from functools import partial
from struct import Struct
from struct import error as StructError
from typing import Any

from confluent_kafka.serialization import MessageField

from kaskade.deserializers.base import DeserializationError, Deserializer


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


class StructDeserializer(Deserializer):
    """Deserializes one big-endian value described by a `struct` format."""

    def __init__(self, struct_format: str):
        self._struct = Struct(struct_format)

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        try:
            return self._struct.unpack(data)[0]
        except StructError as ex:
            raise DeserializationError(str(ex)) from ex


BooleanDeserializer = partial(StructDeserializer, ">?")
FloatDeserializer = partial(StructDeserializer, ">f")
DoubleDeserializer = partial(StructDeserializer, ">d")
LongDeserializer = partial(StructDeserializer, ">q")
IntegerDeserializer = partial(StructDeserializer, ">i")
