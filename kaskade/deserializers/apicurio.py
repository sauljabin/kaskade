import json
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

import grpc_tools  # type: ignore[import-untyped]
from confluent_kafka.serialization import MessageField
from fastavro import parse_schema, schemaless_reader
from google.protobuf.descriptor_pb2 import FileDescriptorProto, FileDescriptorSet
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message_factory import GetMessageClass
from grpc_tools import protoc
from jsonschema.exceptions import SchemaError, ValidationError  # type: ignore[import-untyped]
from jsonschema.validators import validator_for  # type: ignore[import-untyped]
from referencing import Registry as JsonSchemaRegistry
from referencing import Resource
from referencing.jsonschema import DRAFT202012

from kaskade import logger
from kaskade.apicurio import (
    APICURIO_CACHE_CAPACITY,
    ApicurioArtifact,
    ApicurioClient,
    ApicurioConfig,
)
from kaskade.cache import LruCache
from kaskade.configs import SCHEMA_REGISTRY_HEADER_SIZE, SCHEMA_REGISTRY_MAGIC_BYTE, SchemaType
from kaskade.deserializers.base import (
    SCHEMA_METADATA_EXCEPTIONS,
    ApicurioRegistrySchema,
    DeserializationError,
    DeserializationResult,
    Deserializer,
    _deserialize_avro,
    _registry_header,
    _require_field,
)
from kaskade.deserializers.protobuf import descriptor_pool, parse_message, parse_type_ref

ArtifactKey = tuple[str, int]


class ApicurioRegistryDeserializer(Deserializer):
    def __init__(self, config: ApicurioConfig):
        self.registry_client = ApicurioClient(config)
        self._protobuf_descriptor_cache: LruCache[
            ArtifactKey, tuple[FileDescriptorProto, DescriptorPool]
        ] = LruCache(APICURIO_CACHE_CAPACITY)
        self._avro_schema_cache: LruCache[ArtifactKey, Any] = LruCache(APICURIO_CACHE_CAPACITY)
        self._json_validator_cache: LruCache[ArtifactKey, Any] = LruCache(APICURIO_CACHE_CAPACITY)

    def close(self) -> None:
        self.registry_client.close()

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        _, artifact, payload = self._artifact(data, topic, context)
        return self._deserialize_content(artifact, payload)

    def deserialize_with_metadata(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> DeserializationResult:
        topic, artifact, payload = self._artifact(data, topic, context)
        content = self._deserialize_content(artifact, payload)
        return DeserializationResult(content, self._resolve_schema(artifact, topic, context))

    def _artifact(
        self, data: bytes, topic: str | None, context: MessageField
    ) -> tuple[str, ApicurioArtifact, bytes]:
        topic = _require_field(topic, context)
        if len(data) <= SCHEMA_REGISTRY_HEADER_SIZE:
            raise DeserializationError(
                f"Expecting Apicurio data framing of length {SCHEMA_REGISTRY_HEADER_SIZE + 1} "
                f"bytes or more but total data size is {len(data)} bytes"
            )
        magic, artifact_id = _registry_header(data)
        if magic != SCHEMA_REGISTRY_MAGIC_BYTE:
            raise DeserializationError(f"Unexpected Apicurio magic byte: {magic}")
        artifact = self.registry_client.get_artifact(artifact_id)
        return topic, artifact, data[SCHEMA_REGISTRY_HEADER_SIZE:]

    def _deserialize_content(self, artifact: ApicurioArtifact, payload: bytes) -> Any:
        match artifact.type:
            case SchemaType.JSON:
                return self._deserialize_json(artifact, payload)
            case SchemaType.AVRO:
                schema = self._avro_schema(artifact)
                return _deserialize_avro(schemaless_reader, BytesIO(payload), schema, None)
            case SchemaType.PROTOBUF:
                return self._deserialize_protobuf(artifact, payload)
            case _:
                raise DeserializationError("Schema type not supported")

    def _deserialize_json(self, artifact: ApicurioArtifact, payload: bytes) -> Any:
        _, json_payload = parse_type_ref(payload)
        try:
            content = json.loads(json_payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            content = json.loads(payload)
        try:
            self._json_validator(artifact).validate(content)
        except ValidationError as ex:
            raise DeserializationError(f"JSON Schema validation failed: {ex.message}") from ex
        return content

    def _avro_schema(self, artifact: ApicurioArtifact) -> Any:
        cache_key = (artifact.id_kind, artifact.id)
        cached = self._avro_schema_cache.get(cache_key)
        if cached is not None:
            return cached
        named_schemas: dict[str, Any] = {}
        visited: set[tuple[str, str, str]] = set()

        def parse_references(current: ApicurioArtifact) -> None:
            for reference in current.references:
                key = (reference.group, reference.artifact, reference.version)
                if key in visited:
                    continue
                visited.add(key)
                referenced = self.registry_client.get_referenced_artifact(
                    reference, SchemaType.AVRO
                )
                parse_references(referenced)
                parse_schema(json.loads(referenced.content), named_schemas=named_schemas)

        try:
            parse_references(artifact)
            schema = parse_schema(json.loads(artifact.content), named_schemas=named_schemas)
        except (json.JSONDecodeError, TypeError, ValueError) as ex:
            raise DeserializationError(f"Invalid Avro schema: {ex}") from ex
        self._avro_schema_cache.put(cache_key, schema)
        return schema

    def _json_validator(self, artifact: ApicurioArtifact) -> Any:
        cache_key = (artifact.id_kind, artifact.id)
        cached = self._json_validator_cache.get(cache_key)
        if cached is not None:
            return cached
        registry = JsonSchemaRegistry()
        visited: set[tuple[str, str, str]] = set()

        def add_references(current: ApicurioArtifact) -> None:
            nonlocal registry
            for reference in current.references:
                key = (reference.group, reference.artifact, reference.version)
                if key in visited:
                    continue
                visited.add(key)
                referenced = self.registry_client.get_referenced_artifact(
                    reference, SchemaType.JSON
                )
                add_references(referenced)
                contents = json.loads(referenced.content)
                registry = registry.with_resource(
                    reference.name,
                    Resource.from_contents(contents, default_specification=DRAFT202012),
                )

        try:
            add_references(artifact)
            schema = json.loads(artifact.content)
            validator_class = validator_for(schema)
            validator_class.check_schema(schema)
            validator = validator_class(schema, registry=registry)
        except (json.JSONDecodeError, SchemaError, TypeError, ValueError) as ex:
            raise DeserializationError(f"Invalid JSON Schema: {ex}") from ex
        self._json_validator_cache.put(cache_key, validator)
        return validator

    def _deserialize_protobuf(self, artifact: ApicurioArtifact, payload: bytes) -> Any:
        descriptor, pool = self._protobuf_descriptors(artifact)
        message_name, message_payload = parse_type_ref(payload)
        if message_name is None:
            if not descriptor.message_type:
                raise DeserializationError("Protobuf schema contains no messages")
            message_name = ".".join(
                filter(None, (descriptor.package, descriptor.message_type[0].name))
            )
            message_payload = payload
        try:
            message_descriptor = pool.FindMessageTypeByName(message_name)
        except KeyError:
            qualified_name = ".".join(filter(None, (descriptor.package, message_name)))
            try:
                message_descriptor = pool.FindMessageTypeByName(qualified_name)
            except KeyError as ex:
                raise DeserializationError(f"Protobuf message not found: {message_name}") from ex
        return parse_message(GetMessageClass(message_descriptor), message_payload)

    def _protobuf_descriptors(
        self, artifact: ApicurioArtifact
    ) -> tuple[FileDescriptorProto, DescriptorPool]:
        cache_key = (artifact.id_kind, artifact.id)
        cached = self._protobuf_descriptor_cache.get(cache_key)
        if cached is not None:
            return cached

        sources: dict[str, str] = {"root.proto": artifact.content}
        self._collect_protobuf_sources(artifact, sources, set())
        descriptors = {descriptor.name: descriptor for descriptor in self._compile(sources).file}
        root_descriptor = descriptors.get("root.proto")
        if root_descriptor is None:
            raise DeserializationError("Compiled Protobuf root descriptor not found")
        result = (root_descriptor, descriptor_pool(root_descriptor, descriptors))
        self._protobuf_descriptor_cache.put(cache_key, result)
        return result

    def _compile(self, sources: dict[str, str]) -> FileDescriptorSet:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in sources.items():
                path = self._safe_proto_path(root, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            descriptor_path = root / "schema.desc"
            bundled_protos = Path(grpc_tools.__file__).parent / "_proto"
            result = protoc.main(
                [
                    "grpc_tools.protoc",
                    f"-I{root}",
                    f"-I{bundled_protos}",
                    f"--descriptor_set_out={descriptor_path}",
                    "--include_imports",
                    "root.proto",
                ]
            )
            if result != 0:
                raise DeserializationError("Invalid Protobuf schema")
            return FileDescriptorSet.FromString(descriptor_path.read_bytes())

    def _collect_protobuf_sources(
        self,
        artifact: ApicurioArtifact,
        sources: dict[str, str],
        visited: set[tuple[str, str, str]],
    ) -> None:
        for reference in artifact.references:
            key = (reference.group, reference.artifact, reference.version)
            if key in visited:
                continue
            visited.add(key)
            referenced = self.registry_client.get_referenced_artifact(
                reference, SchemaType.PROTOBUF
            )
            sources[reference.name] = referenced.content
            self._collect_protobuf_sources(referenced, sources, visited)

    @staticmethod
    def _safe_proto_path(root: Path, name: str) -> Path:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise DeserializationError(f"Unsafe Protobuf reference name: {name}")
        return root / relative

    def _resolve_schema(
        self,
        artifact: ApicurioArtifact,
        topic: str,
        context: MessageField,
    ) -> ApicurioRegistrySchema:
        result = ApicurioRegistrySchema(
            id=artifact.id,
            id_kind=artifact.id_kind,
            type=artifact.type,
        )
        try:
            registrations = self.registry_client.get_metadata(artifact.id)
            candidates = [
                value for value in registrations if value.get("artifactId") and value.get("version")
            ]
            conventional_artifact = f"{topic}-{context.name.lower()}"
            conventional = [
                value for value in candidates if value.get("artifactId") == conventional_artifact
            ]
            selected = conventional[0] if len(conventional) == 1 else None
            if selected is None and len(candidates) == 1:
                selected = candidates[0]
            if selected is not None:
                result = ApicurioRegistrySchema(
                    id=artifact.id,
                    id_kind=artifact.id_kind,
                    type=artifact.type,
                    group=str(selected.get("groupId") or "default"),
                    artifact=str(selected["artifactId"]),
                    version=str(selected["version"]),
                )
        except SCHEMA_METADATA_EXCEPTIONS as ex:
            logger.warning(
                "schema metadata lookup failed schema_id=%d topic=%s field=%s error=%s",
                artifact.id,
                topic,
                context.name,
                ex,
            )
        return result
