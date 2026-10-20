"""Protobuf encoding of the JSON content the consumer shows, plus Registry message framing."""

import re
from typing import Any

from google.protobuf.descriptor import Descriptor
from google.protobuf.descriptor_pb2 import FileDescriptorProto
from google.protobuf.json_format import ParseDict, ParseError
from google.protobuf.message import EncodeError, Message

from kaskade.serializers.base import SerializationError

FAILED_FIELD = re.compile(r"Failed to parse (\w+) field")
# An Apicurio type reference stores the message name in field 1 (wire type 2).
TYPE_REF_NAME_TAG = 0x0A


def encode_protobuf(message_class: type[Message], content: Any) -> bytes:
    """Parse `content` like MessageToDict's output, the inverse the consumer applies."""
    name = message_class.DESCRIPTOR.full_name
    if not isinstance(content, dict):
        raise SerializationError(f"Expected a JSON object for Protobuf message {name}")
    message = message_class()
    try:
        ParseDict(content, message)
        return message.SerializeToString()
    except ParseError as ex:
        raise SerializationError(_parse_problem(name, str(ex))) from None
    except EncodeError:
        raise SerializationError(f"Protobuf message {name} is missing required fields") from None


def _parse_problem(name: str, message: str) -> str:
    """Keep the field path from the parser's message and drop the values it quotes."""
    path = ".".join(FAILED_FIELD.findall(message))
    if "has no field named" in message:
        location = f" in {path}" if path else ""
        return f"Doesn't match Protobuf message {name}: unknown field{location}"
    if path:
        return f"Doesn't match Protobuf message {name}: invalid value for {path}"
    return f"Doesn't match Protobuf message {name}"


def message_indexes(root: FileDescriptorProto, descriptor: Descriptor) -> list[int]:
    """The path of indexes from the root file's top-level messages to `descriptor`."""
    package = root.package
    if descriptor.file.package != package or descriptor.file.name != root.name:
        raise SerializationError(
            f"Protobuf message {descriptor.full_name} isn't declared in the subject's schema"
        )
    relative = descriptor.full_name.removeprefix(f"{package}.") if package else descriptor.full_name
    indexes: list[int] = []
    messages = root.message_type
    for name in relative.split("."):
        names = [message.name for message in messages]
        index = names.index(name)
        indexes.append(index)
        messages = messages[index].nested_type
    return indexes


def confluent_message_indexes(root: FileDescriptorProto, descriptor: Descriptor) -> bytes:
    """Confluent's zigzag varint index array; the first message is written as one 0."""
    indexes = message_indexes(root, descriptor)
    if indexes == [0]:
        return b"\x00"
    return b"".join(_varint(_zigzag(value)) for value in (len(indexes), *indexes))


def apicurio_type_ref(descriptor: Descriptor) -> bytes:
    """Apicurio's length-delimited reference naming the message within its package."""
    package = descriptor.file.package
    name = descriptor.full_name.removeprefix(f"{package}.") if package else descriptor.full_name
    encoded = name.encode("utf-8")
    reference = bytes([TYPE_REF_NAME_TAG]) + _varint(len(encoded)) + encoded
    return _varint(len(reference)) + reference


def _zigzag(value: int) -> int:
    return (value << 1) ^ (value >> 63)


def _varint(value: int) -> bytes:
    encoded = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            encoded.append(byte | 0x80)
        else:
            encoded.append(byte)
            return bytes(encoded)
