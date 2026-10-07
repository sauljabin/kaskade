from base64 import b64decode
from binascii import Error as BinasciiError
from typing import Any

from confluent_kafka.schema_registry import Schema, SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer as ConfluentAvroDeserializer
from confluent_kafka.schema_registry.json_schema import (
    JSONDeserializer as ConfluentJsonDeserializer,
)
from confluent_kafka.serialization import MessageField, SerializationContext
from google.protobuf.descriptor_pb2 import FileDescriptorProto
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message import DecodeError
from google.protobuf.message_factory import GetMessageClass

from kaskade import logger
from kaskade.configs import SCHEMA_REGISTRY_HEADER_SIZE, SCHEMA_REGISTRY_MAGIC_BYTE, SchemaType
from kaskade.deserializers.base import (
    SCHEMA_METADATA_EXCEPTIONS,
    DeserializationError,
    DeserializationResult,
    Deserializer,
    RegistrySchema,
    _deserialize_avro,
    _registry_header,
    _require_field,
)
from kaskade.deserializers.protobuf import (
    descriptor_pool,
    message_name,
    parse_message,
    parse_message_indexes,
)


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

    def close(self) -> None:
        self.registry_client.close()

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        topic, schema_id, schema_type = self._schema(data, topic, context)
        return self._deserialize_content(data, topic, context, schema_id, schema_type)

    def deserialize_with_metadata(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> DeserializationResult:
        topic, schema_id, schema_type = self._schema(data, topic, context)
        content = self._deserialize_content(data, topic, context, schema_id, schema_type)
        return DeserializationResult(
            content,
            self._resolve_schema(schema_id, schema_type, topic, context),
        )

    def _schema(
        self,
        data: bytes,
        topic: str | None,
        context: MessageField,
    ) -> tuple[str, int, str]:
        topic = _require_field(topic, context)

        minimum_length = SCHEMA_REGISTRY_HEADER_SIZE + 1
        if len(data) < minimum_length:
            raise DeserializationError(
                f"Expecting data framing of length {minimum_length} bytes or more but total "
                f"data size is {len(data)} bytes. This message was not produced with a "
                "Confluent Schema Registry serializer"
            )

        magic, schema_id = _registry_header(data)
        if magic != SCHEMA_REGISTRY_MAGIC_BYTE:
            raise DeserializationError(
                f"Unexpected magic byte {magic}. This message was not produced with a "
                "Confluent Schema Registry serializer"
            )

        schema = self._writer_schema_cache.get(schema_id)
        if schema is None:
            schema = self.registry_client.get_schema(schema_id)
            if schema.schema_type is not None and schema.schema_type.upper() == SchemaType.PROTOBUF:
                # The client caches by schema ID without considering the requested
                # format, so clear its cache before asking for the descriptor form.
                self.registry_client.clear_caches()  # type: ignore[no-untyped-call]
                schema = self.registry_client.get_schema(schema_id, fmt="serialized")
            self._writer_schema_cache[schema_id] = schema
        if schema.schema_type is None:
            raise DeserializationError("Schema type not supported")
        return topic, schema_id, schema.schema_type.upper()

    def _deserialize_content(
        self,
        data: bytes,
        topic: str,
        context: MessageField,
        schema_id: int,
        schema_type: str,
    ) -> Any:
        match schema_type:
            case SchemaType.JSON:
                return self.json_deserializer(data, SerializationContext(topic, context))
            case SchemaType.AVRO:
                return _deserialize_avro(
                    self.avro_deserializer,
                    data,
                    SerializationContext(topic, context),
                )
            case SchemaType.PROTOBUF:
                return self._deserialize_protobuf(data, schema_id)
            case _:
                raise DeserializationError("Schema type not supported")

    def _deserialize_protobuf(self, data: bytes, schema_id: int) -> Any:
        descriptor, pool = self._protobuf_descriptors(schema_id)
        message_indexes, payload = parse_message_indexes(data[SCHEMA_REGISTRY_HEADER_SIZE:])
        name = message_name(descriptor, message_indexes)
        try:
            message_class = GetMessageClass(pool.FindMessageTypeByName(name))
        except KeyError as ex:
            raise DeserializationError(f"Protobuf message not found: {name}") from ex
        return parse_message(message_class, payload)

    def _protobuf_descriptors(self, schema_id: int) -> tuple[FileDescriptorProto, DescriptorPool]:
        cached = self._protobuf_descriptor_cache.get(schema_id)
        if cached is not None:
            return cached

        schema = self._writer_schema_cache[schema_id]
        descriptors: dict[str, FileDescriptorProto] = {}
        root = self._collect_protobuf_descriptors(schema, "default", descriptors)
        result = (root, descriptor_pool(root, descriptors))
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
