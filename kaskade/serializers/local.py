"""Avro and Protobuf serializers that encode with local schema files, without framing."""

from collections.abc import Mapping
from pathlib import Path

from google.protobuf.message import Message

from kaskade.schemas import SchemaError
from kaskade.schemas.avro import load_avro_schema
from kaskade.schemas.protobuf import load_message_classes
from kaskade.serializers.avro import encode_avro
from kaskade.serializers.base import JsonDocumentSerializer, parse_json
from kaskade.serializers.protobuf import encode_protobuf


class AvroSerializer(JsonDocumentSerializer):
    def __init__(self, schema_path: str) -> None:
        self._schema = load_avro_schema(schema_path)
        self.label = f"AVRO · {Path(schema_path).name}"

    def serialize(self, text: str) -> bytes:
        return encode_avro(self._schema, parse_json(text))


class ProtobufSerializer(JsonDocumentSerializer):
    def __init__(self, protobuf_config: Mapping[str, str], message_name: str) -> None:
        self._message_class = local_message_class(protobuf_config, message_name)
        self.label = f"PROTOBUF · {message_name}"

    def serialize(self, text: str) -> bytes:
        return encode_protobuf(self._message_class, parse_json(text))


def local_message_class(protobuf_config: Mapping[str, str], message_name: str) -> type[Message]:
    """Find a message in the `descriptor=` set or the compiled `source=` file."""
    message_class = load_message_classes(protobuf_config).get(message_name)
    if message_class is None:
        path = protobuf_config.get("source", protobuf_config.get("descriptor"))
        raise SchemaError(f"Protobuf message {message_name} isn't in {path}")
    return message_class
