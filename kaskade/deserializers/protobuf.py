"""Protobuf helpers shared by the Registry and local deserializers."""

from typing import Any

from google.protobuf.descriptor_pb2 import DescriptorProto, FileDescriptorProto
from google.protobuf.descriptor_pool import Default as DefaultDescriptorPool
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message

from kaskade.deserializers.base import DeserializationError

# Upper bound on the message-index array length in Confluent Protobuf framing.
MAX_MESSAGE_INDEXES = 100000
# A varint encodes up to 64 bits in at most 10 bytes of 7 bits each.
VARINT_MAX_BYTES = 10
# An Apicurio type reference stores the message name in field 1 (wire type 2).
TYPE_REF_NAME_TAG = 10


def message_to_dict(message: Message) -> dict[str, Any]:
    return MessageToDict(message, always_print_fields_with_no_presence=True)


def parse_message(message_class: type[Message], payload: bytes) -> dict[str, Any]:
    message = message_class()
    message.ParseFromString(payload)
    return message_to_dict(message)


def descriptor_pool(
    root: FileDescriptorProto, descriptors: dict[str, FileDescriptorProto]
) -> DescriptorPool:
    """Build a pool from `root` and its dependencies.

    Dependencies missing from `descriptors` come from the well-known types bundled
    with protobuf.
    """
    pool = DescriptorPool()
    _add_descriptor(root, descriptors, pool, set(), set())
    return pool


def _add_descriptor(
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
            _add_descriptor(referenced, descriptors, pool, added, visiting)
        else:
            _add_default_descriptor(dependency, pool, added)
    try:
        pool.Add(descriptor)
    except (TypeError, ValueError) as ex:
        raise DeserializationError(f"Invalid Protobuf descriptor: {descriptor.name}") from ex
    visiting.remove(descriptor.name)
    added.add(descriptor.name)


def _add_default_descriptor(name: str, pool: DescriptorPool, added: set[str]) -> None:
    if name in added:
        return
    try:
        descriptor = DefaultDescriptorPool().FindFileByName(name)
    except KeyError as ex:
        raise DeserializationError(f"Protobuf schema reference not found: {name}") from ex
    for dependency in descriptor.dependencies:
        _add_default_descriptor(dependency.name, pool, added)
    pool.AddSerializedFile(descriptor.serialized_pb)
    added.add(name)


def _read_varint(data: bytes, offset: int, label: str = "varint") -> tuple[int, int]:
    """Return an unsigned varint and the offset after it."""
    value = 0
    for shift in range(0, 7 * VARINT_MAX_BYTES, 7):
        if offset >= len(data):
            raise DeserializationError(f"Unexpected EOF while reading Protobuf {label}")
        current = data[offset]
        offset += 1
        value |= (current & 0x7F) << shift
        if not current & 0x80:
            return value, offset
    raise DeserializationError(f"Invalid Protobuf {label}")


def _read_message_index(data: bytes, offset: int) -> tuple[int, int]:
    value, offset = _read_varint(data, offset, "message index")
    return (value >> 1) ^ -(value & 1), offset


def parse_message_indexes(data: bytes) -> tuple[list[int], bytes]:
    """Split Confluent's zigzag-encoded message indexes from the message payload."""
    size, offset = _read_message_index(data, 0)
    if size < 0 or size > MAX_MESSAGE_INDEXES:
        raise DeserializationError("Invalid Protobuf message index array length")
    if size == 0:
        return [0], data[offset:]

    indexes = []
    for _ in range(size):
        index, offset = _read_message_index(data, offset)
        indexes.append(index)
    if any(index < 0 for index in indexes):
        raise DeserializationError("Invalid Protobuf message index")
    return indexes, data[offset:]


def message_name(descriptor: FileDescriptorProto, indexes: list[int]) -> str:
    """Resolve Confluent message indexes to a fully qualified message name."""
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


def parse_type_ref(payload: bytes) -> tuple[str | None, bytes]:
    """Split an optional Apicurio type reference from the message payload.

    Returns no name and the unchanged payload when the payload does not start
    with a type reference.
    """
    try:
        message_size, offset = _read_varint(payload, 0)
        end = offset + message_size
        if message_size <= 0 or end > len(payload):
            return None, payload
        ref = payload[offset:end]
        tag, position = _read_varint(ref, 0)
        if tag != TYPE_REF_NAME_TAG:
            return None, payload
        name_size, position = _read_varint(ref, position)
        name_end = position + name_size
        if name_end > len(ref):
            return None, payload
        return ref[position:name_end].decode("utf-8"), payload[end:]
    except (DeserializationError, UnicodeDecodeError):
        return None, payload
