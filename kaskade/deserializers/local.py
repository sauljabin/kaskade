import json
from io import BytesIO
from typing import Any, cast

from confluent_kafka.schema_registry.protobuf import (
    ProtobufDeserializer as ConfluentProtobufDeserializer,
)
from confluent_kafka.serialization import MessageField, SerializationContext
from fastavro import schemaless_reader
from fastavro.schema import load_schema
from google.protobuf.message import Message

from kaskade.configs import (
    APICURIO_OPTION,
    CONFLUENT_OPTION,
    REGISTRY_PROVIDERS,
    SCHEMA_REGISTRY_HEADER_SIZE,
)
from kaskade.deserializers.base import (
    DeserializationError,
    Deserializer,
    _deserialize_avro,
    _has_registry_header,
    _require_context,
    _require_field,
    _scoped_property,
)
from kaskade.deserializers.protobuf import message_to_dict, parse_message, parse_type_ref
from kaskade.schemas.json_schema import load_json_schema, validation_error
from kaskade.schemas.protobuf import load_message_classes


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


class JsonDeserializer(Deserializer):
    """Parse JSON and, when the field has a local JSON Schema, validate it."""

    def __init__(self, json_config: dict[str, str] | None = None):
        self.config = json_config or {}
        self._validators = {
            field: load_json_schema(self.config[name])
            for field, name in ((MessageField.KEY, "key"), (MessageField.VALUE, "value"))
            if name in self.config
        }

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        content = json.loads(_payload(data, self.config, context, "JSON"))
        validator = self._validators.get(context)
        if validator is not None and (error := validation_error(validator, content)) is not None:
            raise DeserializationError(error)
        return content


class AvroDeserializer(Deserializer):
    def __init__(self, avro_config: dict[str, str]):
        self.config = avro_config
        self.key_path = avro_config.get("key")
        self.value_path = avro_config.get("value")
        self._schemas: dict[str, Any] = {}

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        _require_context(context)
        schema_path = self.key_path if context == MessageField.KEY else self.value_path
        if schema_path is None:
            raise DeserializationError(f"Avro schema was not provided for context {context.name}")

        payload = _payload(data, self.config, context, "Avro")
        return _deserialize_avro(
            schemaless_reader, BytesIO(payload), self._schema(schema_path), None
        )

    def _schema(self, schema_path: str) -> Any:
        schema = self._schemas.get(schema_path)
        if schema is None:
            schema = load_schema(schema_path)
            self._schemas[schema_path] = schema
        return schema


class ProtobufDeserializer(Deserializer):
    def __init__(self, protobuf_config: dict[str, str]):
        self.config = protobuf_config
        self.descriptor_path = protobuf_config.get("descriptor")
        self.key_class = protobuf_config.get("key")
        self.value_class = protobuf_config.get("value")
        self.descriptor_classes: dict[str, type[Message]] | None = None
        self._confluent_deserializers: dict[type[Message], ConfluentProtobufDeserializer] = {}

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        topic = _require_field(topic, context)
        message_class = self._message_class(context)
        framing = _scoped_property(self.config, "framing", context, "raw")
        if framing == CONFLUENT_OPTION:
            return self._deserialize_confluent(data, topic, context, message_class)
        if framing == APICURIO_OPTION:
            _, payload = parse_type_ref(_payload(data, self.config, context, "Protobuf"))
        elif framing == "raw":
            payload = data
        else:
            raise DeserializationError(f"Unsupported Protobuf framing: {framing}")
        return parse_message(message_class, payload)

    def _message_class(self, context: MessageField) -> type[Message]:
        class_name = self.key_class if context == MessageField.KEY else self.value_class
        if class_name is None:
            raise DeserializationError(
                f"Protobuf message name not provided for context {context.name}"
            )
        if self.descriptor_path is None:
            raise DeserializationError("Descriptor not found")
        if self.descriptor_classes is None:
            self.descriptor_classes = load_message_classes(self.descriptor_path)
        message_class = self.descriptor_classes.get(class_name)
        if message_class is None:
            raise DeserializationError("Deserialization class not found")
        return message_class

    def _deserialize_confluent(
        self,
        data: bytes,
        topic: str,
        context: MessageField,
        message_class: type[Message],
    ) -> Any:
        deserializer = self._confluent_deserializers.get(message_class)
        if deserializer is None:
            deserializer = ConfluentProtobufDeserializer(
                message_class, {"use.deprecated.format": False}
            )
            self._confluent_deserializers[message_class] = deserializer
        # Confluent annotates the result as bytes, but it returns the parsed message.
        message = cast(Message, deserializer(data, SerializationContext(topic, context)))
        return message_to_dict(message)
