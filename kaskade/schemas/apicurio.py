"""Apicurio Registry artifacts parsed with their references."""

import json
from typing import Any

from google.protobuf.descriptor_pb2 import FileDescriptorProto
from google.protobuf.descriptor_pool import DescriptorPool

from kaskade.apicurio import APICURIO_CACHE_CAPACITY, ApicurioArtifact, ApicurioClient
from kaskade.cache import LruCache
from kaskade.configs import SchemaType
from kaskade.schemas.avro import parse_avro_schema
from kaskade.schemas.errors import SchemaError
from kaskade.schemas.json_schema import json_validator
from kaskade.schemas.protobuf import ROOT_PROTO, compile_sources

ArtifactKey = tuple[str, int]
ReferenceKey = tuple[str, str, str]


class ApicurioSchemas:
    """Parse and cache artifacts by ID kind and ID."""

    def __init__(self, client: ApicurioClient) -> None:
        self.client = client
        self._protobuf: LruCache[ArtifactKey, tuple[FileDescriptorProto, DescriptorPool]] = (
            LruCache(APICURIO_CACHE_CAPACITY)
        )
        self._avro: LruCache[ArtifactKey, Any] = LruCache(APICURIO_CACHE_CAPACITY)
        self._json: LruCache[ArtifactKey, Any] = LruCache(APICURIO_CACHE_CAPACITY)

    def avro_schema(self, artifact: ApicurioArtifact) -> Any:
        cache_key = (artifact.id_kind, artifact.id)
        cached = self._avro.get(cache_key)
        if cached is None:
            references: list[str] = []
            self._collect_contents(artifact, SchemaType.AVRO, references, set())
            cached = parse_avro_schema(artifact.content, references)
            self._avro.put(cache_key, cached)
        return cached

    def json_validator(self, artifact: ApicurioArtifact) -> Any:
        cache_key = (artifact.id_kind, artifact.id)
        cached = self._json.get(cache_key)
        if cached is None:
            resources: dict[str, Any] = {}
            self._collect_json(artifact, resources, set())
            cached = json_validator(_json(artifact.content), resources)
            self._json.put(cache_key, cached)
        return cached

    def protobuf_descriptors(
        self, artifact: ApicurioArtifact
    ) -> tuple[FileDescriptorProto, DescriptorPool]:
        cache_key = (artifact.id_kind, artifact.id)
        cached = self._protobuf.get(cache_key)
        if cached is None:
            sources: dict[str, str] = {ROOT_PROTO: artifact.content}
            self._collect_protobuf(artifact, sources, set())
            cached = compile_sources(sources)
            self._protobuf.put(cache_key, cached)
        return cached

    def _collect_contents(
        self,
        artifact: ApicurioArtifact,
        artifact_type: SchemaType,
        contents: list[str],
        visited: set[ReferenceKey],
    ) -> None:
        """Append referenced artifact contents, dependencies first."""
        for reference in artifact.references:
            key = (reference.group, reference.artifact, reference.version)
            if key in visited:
                continue
            visited.add(key)
            referenced = self.client.get_referenced_artifact(reference, artifact_type)
            self._collect_contents(referenced, artifact_type, contents, visited)
            contents.append(referenced.content)

    def _collect_json(
        self,
        artifact: ApicurioArtifact,
        resources: dict[str, Any],
        visited: set[ReferenceKey],
    ) -> None:
        for reference in artifact.references:
            key = (reference.group, reference.artifact, reference.version)
            if key in visited:
                continue
            visited.add(key)
            referenced = self.client.get_referenced_artifact(reference, SchemaType.JSON)
            self._collect_json(referenced, resources, visited)
            resources[reference.name] = _json(referenced.content)

    def _collect_protobuf(
        self,
        artifact: ApicurioArtifact,
        sources: dict[str, str],
        visited: set[ReferenceKey],
    ) -> None:
        for reference in artifact.references:
            key = (reference.group, reference.artifact, reference.version)
            if key in visited:
                continue
            visited.add(key)
            referenced = self.client.get_referenced_artifact(reference, SchemaType.PROTOBUF)
            sources[reference.name] = referenced.content
            self._collect_protobuf(referenced, sources, visited)


def _json(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError as ex:
        raise SchemaError(f"Invalid JSON Schema: {ex.msg}") from ex
