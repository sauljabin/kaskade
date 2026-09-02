import json
import tempfile
from abc import ABC, abstractmethod
from base64 import b64decode
from binascii import Error as BinasciiError
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from io import BytesIO
from pathlib import Path
from struct import error as StructError
from struct import unpack
from typing import Any

import grpc_tools  # type: ignore[import-untyped]
from confluent_kafka.schema_registry import Schema, SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer as ConfluentAvroDeserializer
from confluent_kafka.schema_registry.error import SchemaRegistryError
from confluent_kafka.schema_registry.json_schema import (
    JSONDeserializer as ConfluentJsonDeserializer,
)
from confluent_kafka.schema_registry.protobuf import (
    ProtobufDeserializer as ConfluentProtobufDeserializer,
)
from confluent_kafka.serialization import MessageField, SerializationContext, SerializationError
from fastavro import parse_schema, schemaless_reader
from google.protobuf.descriptor_pb2 import DescriptorProto, FileDescriptorProto, FileDescriptorSet
from google.protobuf.descriptor_pool import Default as DefaultDescriptorPool
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError, Message
from google.protobuf.message_factory import GetMessageClass, GetMessages
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
    ApicurioRegistryError,
)
from kaskade.configs import (
    APICURIO,
    APICURIO_OPTION,
    CONFLUENT,
    CONFLUENT_OPTION,
    REGISTRY_PROVIDERS,
    SCHEMA_REGISTRY_HEADER_SIZE,
    SCHEMA_REGISTRY_MAGIC_BYTE,
)
from kaskade.utils import avro_to_py, file_to_bytes, unpack_bytes


class DeserializationError(Exception):
    """Raised when configuration, framing, or payload data cannot be deserialized."""


def _unpack_payload(struct_format: str, data: bytes) -> Any:
    try:
        return unpack_bytes(struct_format, data)
    except StructError as ex:
        raise DeserializationError(str(ex)) from ex


def _deserialize_avro(deserialize: Callable[..., Any], *args: Any) -> Any:
    try:
        return deserialize(*args)
    except IndexError as ex:
        raise DeserializationError(str(ex)) from ex


DESERIALIZATION_EXCEPTIONS: tuple[type[Exception], ...] = (
    DeserializationError,
    EOFError,
    OSError,
    ValueError,
    SchemaRegistryError,
    SerializationError,
    DecodeError,
    ApicurioRegistryError,
)
SCHEMA_METADATA_EXCEPTIONS = DESERIALIZATION_EXCEPTIONS + (AttributeError, TypeError)


class Deserialization(Enum):
    BYTES = auto()
    BOOLEAN = auto()
    STRING = auto()
    LONG = auto()
    INTEGER = auto()
    DOUBLE = auto()
    FLOAT = auto()
    JSON = auto()
    AVRO = auto()
    PROTOBUF = auto()
    REGISTRY = auto()

    def __str__(self) -> str:
        return self.name.lower()

    def __repr__(self) -> str:
        return str(self)

    @classmethod
    def from_str(cls, value: str) -> "Deserialization":
        return Deserialization[value.upper()]

    @classmethod
    def str_list(cls) -> list[str]:
        return [str(name) for name in Deserialization]


class BytesEncoding(Enum):
    BASE64 = auto()
    HEX = auto()
    BYTE_ARRAY = auto()
    ESCAPED = auto()

    def __str__(self) -> str:
        return self.name.lower().replace("_", "-")

    @classmethod
    def from_str(cls, value: str) -> "BytesEncoding":
        return cls[value.upper().replace("-", "_")]

    @classmethod
    def from_config(
        cls,
        config: dict[str, str],
        context: MessageField = MessageField.NONE,
    ) -> "BytesEncoding":
        return cls.from_str(_scoped_property(config, "encoding", context, str(cls.BASE64)))


@dataclass(frozen=True)
class RegistrySchema:
    id: int
    subject: str
    version: int
    type: str

    def dict(self) -> dict[str, int | str]:
        return {
            "provider": CONFLUENT,
            "id": self.id,
            "subject": self.subject,
            "version": self.version,
            "type": self.type,
        }


@dataclass(frozen=True)
class ApicurioRegistrySchema:
    id: int
    id_kind: str
    group: str
    artifact: str
    version: str
    type: str

    def dict(self) -> dict[str, int | str]:
        return {
            "provider": APICURIO,
            "id": self.id,
            "id_kind": self.id_kind,
            "group": self.group,
            "artifact": self.artifact,
            "version": self.version,
            "type": self.type,
        }


@dataclass(frozen=True)
class DeserializationResult:
    content: Any
    schema: RegistrySchema | ApicurioRegistrySchema | None = None


class Deserializer(ABC):
    @abstractmethod
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        pass

    def deserialize_with_metadata(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> DeserializationResult:
        return DeserializationResult(self.deserialize(data, topic, context))


class DefaultDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return data


class StringDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return data.decode("utf-8")


class BooleanDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return _unpack_payload(">?", data)


class FloatDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return _unpack_payload(">f", data)


class DoubleDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return _unpack_payload(">d", data)


class LongDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return _unpack_payload(">q", data)


class IntegerDeserializer(Deserializer):
    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return _unpack_payload(">i", data)


class JsonDeserializer(Deserializer):
    def __init__(self, json_config: dict[str, str] | None = None):
        self.config = json_config or {}

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return json.loads(_payload(data, self.config, context, "JSON"))


class ConfluentRegistryDeserializer(Deserializer):
    def __init__(self, registry_config: dict[str, str]):
        confluent_config = {
            key: value for key, value in registry_config.items() if key != "provider"
        }
        self.registry_client = SchemaRegistryClient(confluent_config)
        self.avro_deserializer = ConfluentAvroDeserializer(self.registry_client)
        self.json_deserializer = ConfluentJsonDeserializer(
            None, schema_registry_client=self.registry_client
        )
        self._writer_schema_cache: dict[int, Schema] = {}
        self._protobuf_descriptor_cache: dict[int, tuple[FileDescriptorProto, DescriptorPool]] = {}
        self._schema_cache: dict[tuple[int, str, MessageField], RegistrySchema | None] = {}

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        schema_id, schema_type = self._schema(data, topic, context)
        return self._deserialize_content(data, topic, context, schema_id, schema_type)

    def deserialize_with_metadata(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> DeserializationResult:
        schema_id, schema_type = self._schema(data, topic, context)
        content = self._deserialize_content(data, topic, context, schema_id, schema_type)
        assert topic is not None
        return DeserializationResult(
            content,
            self._resolve_schema(schema_id, schema_type, topic, context),
        )

    def _schema(
        self,
        data: bytes,
        topic: str | None,
        context: MessageField,
    ) -> tuple[int, str]:
        if topic is None:
            raise DeserializationError("Topic name needed")

        if context == MessageField.NONE:
            raise DeserializationError("Context is needed: KEY or VALUE")

        minimum_length = SCHEMA_REGISTRY_HEADER_SIZE + 1
        if len(data) < minimum_length:
            raise DeserializationError(
                f"Expecting data framing of length {minimum_length} bytes or more but total data size is {len(data)} bytes. This message was not produced with a Confluent Schema Registry serializer"
            )

        magic, schema_id = unpack(">bI", data[:SCHEMA_REGISTRY_HEADER_SIZE])
        if magic != SCHEMA_REGISTRY_MAGIC_BYTE:
            raise DeserializationError(
                f"Unexpected magic byte {magic}. This message was not produced with a Confluent Schema Registry serializer"
            )

        schema = self._writer_schema_cache.get(schema_id)
        if schema is None:
            schema = self.registry_client.get_schema(schema_id)
            if schema.schema_type is not None and schema.schema_type.upper() == "PROTOBUF":
                # The client caches by schema ID without considering the requested
                # format, so clear its cache before asking for the descriptor form.
                self.registry_client.clear_caches()  # type: ignore[no-untyped-call]
                schema = self.registry_client.get_schema(schema_id, fmt="serialized")
            self._writer_schema_cache[schema_id] = schema
        if schema.schema_type is None:
            raise DeserializationError("Schema type not supported")
        return schema_id, schema.schema_type.upper()

    def _deserialize_content(
        self,
        data: bytes,
        topic: str | None,
        context: MessageField,
        schema_id: int,
        schema_type: str,
    ) -> Any:
        assert topic is not None
        match schema_type:
            case "JSON":
                return self.json_deserializer(data, SerializationContext(topic, context))
            case "AVRO":
                return _deserialize_avro(
                    self.avro_deserializer,
                    data,
                    SerializationContext(topic, context),
                )
            case "PROTOBUF":
                return self._deserialize_protobuf(data, schema_id)
            case _:
                raise DeserializationError("Schema type not supported")

    def _deserialize_protobuf(self, data: bytes, schema_id: int) -> Any:
        descriptor, pool = self._protobuf_descriptors(schema_id)
        message_indexes, payload = self._protobuf_payload(data)
        message_name = self._protobuf_message_name(descriptor, message_indexes)
        try:
            message_class = GetMessageClass(pool.FindMessageTypeByName(message_name))
        except KeyError as ex:
            raise DeserializationError(f"Protobuf message not found: {message_name}") from ex

        message = message_class()
        message.ParseFromString(payload)
        return MessageToDict(message, always_print_fields_with_no_presence=True)

    def _protobuf_descriptors(self, schema_id: int) -> tuple[FileDescriptorProto, DescriptorPool]:
        cached = self._protobuf_descriptor_cache.get(schema_id)
        if cached is not None:
            return cached

        schema = self._writer_schema_cache[schema_id]
        descriptors: dict[str, FileDescriptorProto] = {}
        root = self._collect_protobuf_descriptors(schema, "default", descriptors)
        pool = DescriptorPool()
        added: set[str] = set()
        visiting: set[str] = set()
        self._add_protobuf_descriptor(root, descriptors, pool, added, visiting)
        result = (root, pool)
        self._protobuf_descriptor_cache[schema_id] = result
        return result

    def _collect_protobuf_descriptors(
        self,
        schema: Schema,
        name: str,
        descriptors: dict[str, FileDescriptorProto],
    ) -> FileDescriptorProto:
        existing = descriptors.get(name)
        if existing is not None:
            return existing

        schema_str = schema.schema_str
        if not isinstance(schema_str, str):
            raise DeserializationError("Protobuf schema is empty")
        descriptor = self._parse_protobuf_descriptor(name, schema_str)
        descriptors[name] = descriptor

        for reference in schema.references or []:
            if reference.name is None or reference.subject is None or reference.version is None:
                raise DeserializationError("Protobuf schema reference is incomplete")
            registered = self.registry_client.get_version(
                reference.subject,
                reference.version,
                deleted=True,
                fmt="serialized",
            )
            self._collect_protobuf_descriptors(registered.schema, reference.name, descriptors)
        return descriptor

    @staticmethod
    def _parse_protobuf_descriptor(name: str, schema_str: str) -> FileDescriptorProto:
        try:
            serialized = b64decode(schema_str.encode("ascii"), validate=True)
            descriptor = FileDescriptorProto.FromString(serialized)
        except (BinasciiError, UnicodeEncodeError, DecodeError) as ex:
            raise DeserializationError("Invalid serialized Protobuf schema") from ex
        descriptor.name = name
        return descriptor

    def _add_protobuf_descriptor(
        self,
        descriptor: FileDescriptorProto,
        descriptors: dict[str, FileDescriptorProto],
        pool: DescriptorPool,
        added: set[str],
        visiting: set[str],
    ) -> None:
        if descriptor.name in added:
            return
        if descriptor.name in visiting:
            raise DeserializationError("Cyclic Protobuf schema reference")

        visiting.add(descriptor.name)
        for dependency in descriptor.dependency:
            referenced = descriptors.get(dependency)
            if referenced is not None:
                self._add_protobuf_descriptor(referenced, descriptors, pool, added, visiting)
            else:
                self._add_default_protobuf_descriptor(dependency, pool, added)
        try:
            pool.Add(descriptor)
        except (TypeError, ValueError) as ex:
            raise DeserializationError(f"Invalid Protobuf descriptor: {descriptor.name}") from ex
        visiting.remove(descriptor.name)
        added.add(descriptor.name)

    @classmethod
    def _add_default_protobuf_descriptor(
        cls,
        name: str,
        pool: DescriptorPool,
        added: set[str],
    ) -> None:
        if name in added:
            return
        try:
            descriptor = DefaultDescriptorPool().FindFileByName(name)
        except KeyError as ex:
            raise DeserializationError(f"Protobuf schema reference not found: {name}") from ex
        for dependency in descriptor.dependencies:
            cls._add_default_protobuf_descriptor(dependency.name, pool, added)
        pool.AddSerializedFile(descriptor.serialized_pb)
        added.add(name)

    @classmethod
    def _protobuf_payload(cls, data: bytes) -> tuple[list[int], bytes]:
        payload = BytesIO(data[SCHEMA_REGISTRY_HEADER_SIZE:])
        size = cls._decode_protobuf_varint(payload)
        if size < 0 or size > 100000:
            raise DeserializationError("Invalid Protobuf message index array length")
        if size == 0:
            return [0], payload.read()

        indexes = [cls._decode_protobuf_varint(payload) for _ in range(size)]
        if any(index < 0 for index in indexes):
            raise DeserializationError("Invalid Protobuf message index")
        return indexes, payload.read()

    @staticmethod
    def _decode_protobuf_varint(payload: BytesIO) -> int:
        value = 0
        shift = 0
        while shift < 70:
            byte = payload.read(1)
            if not byte:
                raise DeserializationError("Unexpected EOF while reading Protobuf message index")
            current = byte[0]
            value |= (current & 0x7F) << shift
            if not current & 0x80:
                return (value >> 1) ^ -(value & 1)
            shift += 7
        raise DeserializationError("Invalid Protobuf message index")

    @staticmethod
    def _protobuf_message_name(
        descriptor: FileDescriptorProto,
        indexes: list[int],
    ) -> str:
        messages = descriptor.message_type
        path: list[str] = []
        message: DescriptorProto | None = None
        for index in indexes:
            if index >= len(messages):
                raise DeserializationError("Protobuf message index is out of range")
            message = messages[index]
            path.append(message.name)
            messages = message.nested_type
        if message is None:
            raise DeserializationError("Protobuf message index is empty")
        return ".".join(filter(None, (descriptor.package, *path)))

    def _resolve_schema(
        self,
        schema_id: int,
        schema_type: str,
        topic: str,
        context: MessageField,
    ) -> RegistrySchema | None:
        cache_key = (schema_id, topic, context)
        if cache_key in self._schema_cache:
            return self._schema_cache[cache_key]

        try:
            registrations = self.registry_client.get_schema_versions(schema_id)
            result = self._select_schema(
                schema_id,
                schema_type,
                topic,
                context,
                registrations,
            )
        except SCHEMA_METADATA_EXCEPTIONS as ex:
            logger.warning(
                "schema metadata lookup failed schema_id=%d topic=%s field=%s error=%s",
                schema_id,
                topic,
                context.name,
                ex,
            )
            result = None

        self._schema_cache[cache_key] = result
        return result

    @staticmethod
    def _select_schema(
        schema_id: int,
        schema_type: str,
        topic: str,
        context: MessageField,
        registrations: list[Any],
    ) -> RegistrySchema | None:
        candidates = [
            registration
            for registration in registrations
            if registration.subject is not None and registration.version is not None
        ]
        selected = candidates[0] if len(candidates) == 1 else None
        if selected is None:
            conventional_subject = f"{topic}-{context.name.lower()}"
            conventional = [
                registration
                for registration in candidates
                if registration.subject == conventional_subject
            ]
            selected = conventional[0] if len(conventional) == 1 else None
        if selected is None:
            return None
        return RegistrySchema(
            id=schema_id,
            subject=selected.subject,
            version=selected.version,
            type=schema_type,
        )


class ApicurioRegistryDeserializer(Deserializer):
    MAGIC_BYTE = 0
    HEADER_SIZE = 5

    def __init__(self, registry_config: dict[str, str]):
        self.registry_client = ApicurioClient(registry_config)
        self._protobuf_descriptor_cache: OrderedDict[
            tuple[str, int], tuple[FileDescriptorProto, DescriptorPool]
        ] = OrderedDict()
        self._avro_schema_cache: OrderedDict[tuple[str, int], Any] = OrderedDict()
        self._json_validator_cache: OrderedDict[tuple[str, int], Any] = OrderedDict()

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        artifact, payload = self._artifact(data, topic, context)
        return self._deserialize_content(artifact, payload)

    def deserialize_with_metadata(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> DeserializationResult:
        artifact, payload = self._artifact(data, topic, context)
        content = self._deserialize_content(artifact, payload)
        assert topic is not None
        return DeserializationResult(content, self._resolve_schema(artifact, topic, context))

    def _artifact(
        self, data: bytes, topic: str | None, context: MessageField
    ) -> tuple[ApicurioArtifact, bytes]:
        if topic is None:
            raise DeserializationError("Topic name needed")
        if context == MessageField.NONE:
            raise DeserializationError("Context is needed: KEY or VALUE")
        if len(data) <= self.HEADER_SIZE:
            raise DeserializationError(
                "Expecting Apicurio data framing of length 6 bytes or more "
                f"but total data size is {len(data)} bytes"
            )
        try:
            magic, artifact_id = unpack(">bI", data[: self.HEADER_SIZE])
        except StructError as ex:
            raise DeserializationError(str(ex)) from ex
        if magic != self.MAGIC_BYTE:
            raise DeserializationError(f"Unexpected Apicurio magic byte: {magic}")
        return self.registry_client.get_artifact(artifact_id), data[self.HEADER_SIZE :]

    def _deserialize_content(self, artifact: ApicurioArtifact, payload: bytes) -> Any:
        match artifact.type:
            case "JSON":
                _, json_payload = self._type_ref(payload)
                try:
                    content = json.loads(json_payload)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    content = json.loads(payload)
                try:
                    self._json_validator(artifact).validate(content)
                except ValidationError as ex:
                    raise DeserializationError(
                        f"JSON Schema validation failed: {ex.message}"
                    ) from ex
                return content
            case "AVRO":
                schema = self._avro_schema(artifact)
                return _deserialize_avro(schemaless_reader, BytesIO(payload), schema, None)
            case "PROTOBUF":
                return self._deserialize_protobuf(artifact, payload)
            case _:
                raise DeserializationError("Schema type not supported")

    def _avro_schema(self, artifact: ApicurioArtifact) -> Any:
        cache_key = (artifact.id_kind, artifact.id)
        cached = self._avro_schema_cache.get(cache_key)
        if cached is not None:
            self._avro_schema_cache.move_to_end(cache_key)
            return cached
        named_schemas: dict[str, Any] = {}
        visited: set[tuple[str, str, str]] = set()

        def parse_references(current: ApicurioArtifact) -> None:
            for reference in current.references:
                key = (reference.group, reference.artifact, reference.version)
                if key in visited:
                    continue
                visited.add(key)
                referenced = self.registry_client.get_referenced_artifact(reference, "AVRO")
                parse_references(referenced)
                parse_schema(json.loads(referenced.content), named_schemas=named_schemas)

        try:
            parse_references(artifact)
            schema = parse_schema(json.loads(artifact.content), named_schemas=named_schemas)
        except (json.JSONDecodeError, TypeError, ValueError) as ex:
            raise DeserializationError(f"Invalid Avro schema: {ex}") from ex
        self._avro_schema_cache[cache_key] = schema
        self._bound_cache(self._avro_schema_cache)
        return schema

    def _json_validator(self, artifact: ApicurioArtifact) -> Any:
        cache_key = (artifact.id_kind, artifact.id)
        cached = self._json_validator_cache.get(cache_key)
        if cached is not None:
            self._json_validator_cache.move_to_end(cache_key)
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
                referenced = self.registry_client.get_referenced_artifact(reference, "JSON")
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
        self._json_validator_cache[cache_key] = validator
        self._bound_cache(self._json_validator_cache)
        return validator

    def _deserialize_protobuf(self, artifact: ApicurioArtifact, payload: bytes) -> Any:
        descriptor, pool = self._protobuf_descriptors(artifact)
        message_name, message_payload = self._type_ref(payload)
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
        message_class = GetMessageClass(message_descriptor)
        message = message_class()
        message.ParseFromString(message_payload)
        return MessageToDict(message, always_print_fields_with_no_presence=True)

    def _protobuf_descriptors(
        self, artifact: ApicurioArtifact
    ) -> tuple[FileDescriptorProto, DescriptorPool]:
        cache_key = (artifact.id_kind, artifact.id)
        cached = self._protobuf_descriptor_cache.get(cache_key)
        if cached is not None:
            self._protobuf_descriptor_cache.move_to_end(cache_key)
            return cached

        sources: dict[str, str] = {"root.proto": artifact.content}
        self._collect_protobuf_sources(artifact, sources, set())
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
            descriptor_set = FileDescriptorSet.FromString(descriptor_path.read_bytes())

        descriptors = {descriptor.name: descriptor for descriptor in descriptor_set.file}
        root_descriptor = descriptors.get("root.proto")
        if root_descriptor is None:
            raise DeserializationError("Compiled Protobuf root descriptor not found")
        pool = DescriptorPool()
        added: set[str] = set()
        visiting: set[str] = set()
        self._add_protobuf_descriptor(root_descriptor, descriptors, pool, added, visiting)
        result_pair = (root_descriptor, pool)
        self._protobuf_descriptor_cache[cache_key] = result_pair
        self._bound_cache(self._protobuf_descriptor_cache)
        return result_pair

    @staticmethod
    def _bound_cache(cache: OrderedDict[Any, Any]) -> None:
        while len(cache) > APICURIO_CACHE_CAPACITY:
            cache.popitem(last=False)

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
            referenced = self.registry_client.get_referenced_artifact(reference, "PROTOBUF")
            sources[reference.name] = referenced.content
            self._collect_protobuf_sources(referenced, sources, visited)

    @staticmethod
    def _safe_proto_path(root: Path, name: str) -> Path:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise DeserializationError(f"Unsafe Protobuf reference name: {name}")
        return root / relative

    def _add_protobuf_descriptor(
        self,
        descriptor: FileDescriptorProto,
        descriptors: dict[str, FileDescriptorProto],
        pool: DescriptorPool,
        added: set[str],
        visiting: set[str],
    ) -> None:
        if descriptor.name in added:
            return
        if descriptor.name in visiting:
            raise DeserializationError("Cyclic Protobuf schema reference")
        visiting.add(descriptor.name)
        for dependency in descriptor.dependency:
            referenced = descriptors.get(dependency)
            if referenced is None:
                raise DeserializationError(f"Protobuf schema reference not found: {dependency}")
            self._add_protobuf_descriptor(referenced, descriptors, pool, added, visiting)
        try:
            pool.Add(descriptor)
        except (TypeError, ValueError) as ex:
            raise DeserializationError(f"Invalid Protobuf descriptor: {descriptor.name}") from ex
        visiting.remove(descriptor.name)
        added.add(descriptor.name)

    @classmethod
    def _type_ref(cls, payload: bytes) -> tuple[str | None, bytes]:
        try:
            message_size, offset = cls._unsigned_varint(payload, 0)
            end = offset + message_size
            if message_size <= 0 or end > len(payload):
                return None, payload
            ref = payload[offset:end]
            tag, position = cls._unsigned_varint(ref, 0)
            if tag != 10:
                return None, payload
            name_size, position = cls._unsigned_varint(ref, position)
            name_end = position + name_size
            if name_end > len(ref):
                return None, payload
            return ref[position:name_end].decode("utf-8"), payload[end:]
        except (DeserializationError, UnicodeDecodeError):
            return None, payload

    @staticmethod
    def _unsigned_varint(data: bytes, offset: int) -> tuple[int, int]:
        value = 0
        shift = 0
        while shift < 35:
            if offset >= len(data):
                raise DeserializationError("Unexpected EOF while reading Protobuf varint")
            current = data[offset]
            offset += 1
            value |= (current & 0x7F) << shift
            if not current & 0x80:
                return value, offset
            shift += 7
        raise DeserializationError("Invalid Protobuf varint")

    def _resolve_schema(
        self,
        artifact: ApicurioArtifact,
        topic: str,
        context: MessageField,
    ) -> ApicurioRegistrySchema | None:
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
            result = None
            if selected is not None:
                result = ApicurioRegistrySchema(
                    id=artifact.id,
                    id_kind=artifact.id_kind,
                    group=str(selected.get("groupId") or "default"),
                    artifact=str(selected["artifactId"]),
                    version=str(selected["version"]),
                    type=artifact.type,
                )
        except SCHEMA_METADATA_EXCEPTIONS as ex:
            logger.warning(
                "schema metadata lookup failed schema_id=%d topic=%s field=%s error=%s",
                artifact.id,
                topic,
                context.name,
                ex,
            )
            result = None
        return result


class RegistryDeserializer(Deserializer):
    """Provider-dispatching Registry deserializer with a stable public facade."""

    _backend: Deserializer

    def __init__(self, registry_config: dict[str, str]):
        provider = registry_config.get("provider", CONFLUENT_OPTION).lower()
        if provider == CONFLUENT_OPTION:
            backend: Deserializer = ConfluentRegistryDeserializer(registry_config)
        elif provider == APICURIO_OPTION:
            backend = ApicurioRegistryDeserializer(registry_config)
        else:
            raise DeserializationError(
                f"Unsupported registry provider: {provider}; expected one of {REGISTRY_PROVIDERS}"
            )
        object.__setattr__(self, "_backend", backend)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._backend, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_backend":
            object.__setattr__(self, name, value)
        else:
            setattr(self._backend, name, value)

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return self._backend.deserialize(data, topic, context)

    def deserialize_with_metadata(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> DeserializationResult:
        return self._backend.deserialize_with_metadata(data, topic, context)


class AvroDeserializer(Deserializer):
    def __init__(self, avro_config: dict[str, str]):
        self.config = avro_config
        self.key_path = avro_config.get("key")
        self.value_path = avro_config.get("value")

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        schema_path: str | None = None

        if context == MessageField.NONE:
            raise DeserializationError("Context is needed: KEY or VALUE")

        if context == MessageField.KEY:
            if self.key_path is None:
                raise DeserializationError("Avro schema was not provided for context KEY")
            schema_path = self.key_path

        if context == MessageField.VALUE:
            if self.value_path is None:
                raise DeserializationError("Avro schema was not provided for context VALUE")
            schema_path = self.value_path

        if schema_path is None:
            raise DeserializationError("Avro schema file not found")

        payload = _payload(data, self.config, context, "Avro")
        return _deserialize_avro(avro_to_py, schema_path, payload)


class ProtobufDeserializer(Deserializer):
    def __init__(self, protobuf_config: dict[str, str]):
        self.config = protobuf_config
        self.descriptor_path = protobuf_config.get("descriptor")
        self.key_class = protobuf_config.get("key")
        self.value_class = protobuf_config.get("value")
        self.descriptor_classes: dict[str, type[Message]] | None = None

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        if topic is None:
            raise DeserializationError("Topic name needed")
        message_class = self._message_class(context)
        framing = _scoped_property(self.config, "framing", context, "raw")
        if framing == CONFLUENT_OPTION:
            return self._deserialize_confluent(data, topic, context, message_class)
        if framing == APICURIO_OPTION:
            payload = _payload(data, self.config, context, "Protobuf")
            _, payload = ApicurioRegistryDeserializer._type_ref(payload)
        elif framing == "raw":
            payload = data
        else:
            raise DeserializationError(f"Unsupported Protobuf framing: {framing}")

        new_message = message_class()
        new_message.ParseFromString(payload)
        return MessageToDict(new_message, always_print_fields_with_no_presence=True)

    def _message_class(self, context: MessageField) -> type[Message]:
        class_name = self._class_name(context)
        if self.descriptor_path is None:
            raise DeserializationError("Descriptor not found")
        if self.descriptor_classes is None:
            descriptor = FileDescriptorSet.FromString(file_to_bytes(self.descriptor_path))
            self.descriptor_classes = GetMessages(descriptor.file)
        message_class = self.descriptor_classes.get(class_name)
        if message_class is None:
            raise DeserializationError("Deserialization class not found")
        return message_class

    def _class_name(self, context: MessageField) -> str:
        if context == MessageField.NONE:
            raise DeserializationError("Context is needed: KEY or VALUE")
        class_name = self.key_class if context == MessageField.KEY else self.value_class
        if class_name is None:
            raise DeserializationError(
                f"Protobuf message name not provided for context {context.name}"
            )
        return class_name

    @staticmethod
    def _deserialize_confluent(
        data: bytes,
        topic: str,
        context: MessageField,
        message_class: type[Message],
    ) -> Any:
        deserializer = ConfluentProtobufDeserializer(
            message_class, {"use.deprecated.format": False}
        )
        message = deserializer(data, SerializationContext(topic, context))
        return MessageToDict(message, always_print_fields_with_no_presence=True)


class DeserializerPool:
    def __init__(
        self,
        registry_config: dict[str, str] | None = None,
        protobuf_config: dict[str, str] | None = None,
        avro_config: dict[str, str] | None = None,
        json_config: dict[str, str] | None = None,
    ):
        self.registry_deserializer: RegistryDeserializer | None = None
        self.protobuf_deserializer: ProtobufDeserializer | None = None
        self.avro_deserializer: AvroDeserializer | None = None

        if registry_config:
            self.registry_deserializer = RegistryDeserializer(registry_config)

        if avro_config:
            self.avro_deserializer = AvroDeserializer(avro_config)

        if protobuf_config:
            self.protobuf_deserializer = ProtobufDeserializer(protobuf_config)

        self.string_deserializer = StringDeserializer()
        self.json_deserializer = JsonDeserializer(json_config)
        self.integer_deserializer = IntegerDeserializer()
        self.float_deserializer = FloatDeserializer()
        self.double_deserializer = DoubleDeserializer()
        self.boolean_deserializer = BooleanDeserializer()
        self.long_deserializer = LongDeserializer()
        self.default_deserializer = DefaultDeserializer()
        self._deserializers: dict[Deserialization, Deserializer | None] = {
            Deserialization.BYTES: self.default_deserializer,
            Deserialization.STRING: self.string_deserializer,
            Deserialization.JSON: self.json_deserializer,
            Deserialization.INTEGER: self.integer_deserializer,
            Deserialization.LONG: self.long_deserializer,
            Deserialization.DOUBLE: self.double_deserializer,
            Deserialization.FLOAT: self.float_deserializer,
            Deserialization.BOOLEAN: self.boolean_deserializer,
            Deserialization.REGISTRY: self.registry_deserializer,
            Deserialization.AVRO: self.avro_deserializer,
            Deserialization.PROTOBUF: self.protobuf_deserializer,
        }

    def get(self, deserialization_format: Deserialization) -> Deserializer:
        try:
            deserializer = self._deserializers[deserialization_format]
        except KeyError as ex:
            raise DeserializationError(
                f"Deserializer not registered: {deserialization_format}"
            ) from ex
        if deserializer is None:
            configured_name = {
                Deserialization.REGISTRY: "Schema Registry",
                Deserialization.AVRO: "Avro",
                Deserialization.PROTOBUF: "Protobuf",
            }[deserialization_format]
            raise DeserializationError(f"{configured_name} is not configured")
        return deserializer


def _has_registry_header(data: bytes) -> bool:
    if len(data) <= SCHEMA_REGISTRY_HEADER_SIZE:
        return False
    magic = int(unpack(">bI", data[:SCHEMA_REGISTRY_HEADER_SIZE])[0])
    return magic == SCHEMA_REGISTRY_MAGIC_BYTE


def _scoped_property(
    config: dict[str, str],
    property_name: str,
    context: MessageField,
    default: str,
) -> str:
    if context != MessageField.NONE:
        scoped_name = f"{context.name.lower()}.{property_name}"
        if scoped_name in config:
            return config[scoped_name]
    return config.get(property_name, default)


def _payload(
    data: bytes,
    config: dict[str, str],
    context: MessageField,
    deserializer_name: str,
) -> bytes:
    framing = _scoped_property(config, "framing", context, "raw")
    if framing == "raw":
        return data
    if framing in REGISTRY_PROVIDERS and _has_registry_header(data):
        return data[SCHEMA_REGISTRY_HEADER_SIZE:]
    if framing in REGISTRY_PROVIDERS:
        raise DeserializationError(
            f"{framing.title()} {deserializer_name} framing header not found"
        )
    raise DeserializationError(f"Unsupported {deserializer_name} framing: {framing}")
