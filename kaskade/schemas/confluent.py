"""Confluent Schema Registry schemas by ID, with their references."""

import json
from base64 import b64decode
from binascii import Error as BinasciiError
from collections.abc import Iterator
from typing import Any

from confluent_kafka.schema_registry import Schema, SchemaRegistryClient
from google.protobuf.descriptor_pb2 import FileDescriptorProto
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message import DecodeError

from kaskade.configs import SchemaType
from kaskade.schemas.avro import parse_avro_schema
from kaskade.schemas.errors import SchemaError
from kaskade.schemas.json_schema import json_validator
from kaskade.schemas.protobuf import descriptor_pool

ROOT_DESCRIPTOR_NAME = "default"


class ConfluentSchemas:
    """Fetch and cache schemas by ID; Protobuf comes in its serialized descriptor form."""

    def __init__(self, client: SchemaRegistryClient) -> None:
        self.client = client
        self._schemas: dict[int, Schema] = {}
        self._protobuf: dict[int, tuple[FileDescriptorProto, DescriptorPool]] = {}
        self._avro: dict[int, Any] = {}
        self._json: dict[int, Any] = {}

    def schema(self, schema_id: int) -> Schema:
        schema = self._schemas.get(schema_id)
        if schema is None:
            schema = self.client.get_schema(schema_id)
            if schema_type(schema) == SchemaType.PROTOBUF:
                # The client caches by schema ID without considering the requested
                # format, so clear its cache before asking for the descriptor form.
                self.client.clear_caches()  # type: ignore[no-untyped-call]
                schema = self.client.get_schema(schema_id, fmt="serialized")
            self._schemas[schema_id] = schema
        return schema

    def schema_type(self, schema_id: int) -> SchemaType:
        result = schema_type(self.schema(schema_id))
        if result is None:
            raise SchemaError("Schema type not supported")
        return result

    def protobuf_descriptors(self, schema_id: int) -> tuple[FileDescriptorProto, DescriptorPool]:
        cached = self._protobuf.get(schema_id)
        if cached is None:
            descriptors: dict[str, FileDescriptorProto] = {}
            root = self._collect_protobuf(self.schema(schema_id), ROOT_DESCRIPTOR_NAME, descriptors)
            cached = (root, descriptor_pool(root, descriptors))
            self._protobuf[schema_id] = cached
        return cached

    def avro_schema(self, schema_id: int) -> Any:
        cached = self._avro.get(schema_id)
        if cached is None:
            schema = self.schema(schema_id)
            references: list[str] = []
            self._collect_contents(schema, references, set())
            cached = parse_avro_schema(_content(schema), references)
            self._avro[schema_id] = cached
        return cached

    def json_validator(self, schema_id: int) -> Any:
        cached = self._json.get(schema_id)
        if cached is None:
            schema = self.schema(schema_id)
            resources: dict[str, Any] = {}
            self._collect_json(schema, resources)
            try:
                contents = json.loads(_content(schema))
            except json.JSONDecodeError as ex:
                raise SchemaError(f"Invalid JSON Schema: {ex.msg}") from ex
            cached = json_validator(contents, resources)
            self._json[schema_id] = cached
        return cached

    def _references(self, schema: Schema, fmt: str | None = None) -> Iterator[tuple[str, Schema]]:
        """Yield each reference's name and the schema it names."""
        for reference in schema.references or []:
            if reference.name is None or reference.subject is None or reference.version is None:
                raise SchemaError("Schema reference is incomplete")
            registered = self.client.get_version(
                reference.subject, reference.version, deleted=True, fmt=fmt
            )
            yield reference.name, registered.schema

    def _collect_contents(self, schema: Schema, contents: list[str], visited: set[str]) -> None:
        """Append referenced schema contents, dependencies first."""
        for name, referenced in self._references(schema):
            if name in visited:
                continue
            visited.add(name)
            self._collect_contents(referenced, contents, visited)
            contents.append(_content(referenced))

    def _collect_json(self, schema: Schema, resources: dict[str, Any]) -> None:
        for name, referenced in self._references(schema):
            if name in resources:
                continue
            try:
                resources[name] = json.loads(_content(referenced))
            except json.JSONDecodeError as ex:
                raise SchemaError(f"Invalid JSON Schema reference {name}") from ex
            self._collect_json(referenced, resources)

    def _collect_protobuf(
        self,
        schema: Schema,
        name: str,
        descriptors: dict[str, FileDescriptorProto],
    ) -> FileDescriptorProto:
        existing = descriptors.get(name)
        if existing is not None:
            return existing

        descriptor = _parse_protobuf_descriptor(name, _content(schema))
        descriptors[name] = descriptor
        for reference_name, referenced in self._references(schema, fmt="serialized"):
            self._collect_protobuf(referenced, reference_name, descriptors)
        return descriptor


def schema_type(schema: Schema) -> SchemaType | None:
    if schema.schema_type is None:
        return None
    try:
        return SchemaType(schema.schema_type.upper())
    except ValueError:
        return None


def _content(schema: Schema) -> str:
    if not isinstance(schema.schema_str, str):
        raise SchemaError("Schema is empty")
    return schema.schema_str


def _parse_protobuf_descriptor(name: str, schema_str: str) -> FileDescriptorProto:
    try:
        serialized = b64decode(schema_str.encode("ascii"), validate=True)
        descriptor = FileDescriptorProto.FromString(serialized)
    except (BinasciiError, UnicodeEncodeError, DecodeError) as ex:
        raise SchemaError("Invalid serialized Protobuf schema") from ex
    descriptor.name = name
    return descriptor
