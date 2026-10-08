"""Producer serializers that turn composer text into Kafka key and value bytes.

They are independent of the consumer deserializers so Producer formats, such as
future Registry serializers, can evolve on their own.
"""

import base64
import binascii
import json
import re
from enum import Enum, auto
from struct import Struct
from typing import Any

from kaskade.deserializers import BytesEncoding

ESCAPE_PATTERN = re.compile(r"\\(\\|x[0-9a-fA-F]{2})")


class SerializationError(ValueError):
    """Raised when composer text is not valid for the selected serializer.

    Messages describe the problem without repeating the content.
    """


class Serialization(Enum):
    STRING = auto()
    BYTES = auto()
    BOOLEAN = auto()
    INTEGER = auto()
    LONG = auto()
    FLOAT = auto()
    DOUBLE = auto()
    JSON = auto()

    def __str__(self) -> str:
        return self.name.lower()

    @classmethod
    def str_list(cls) -> list[str]:
        return [str(serialization) for serialization in cls]

    @classmethod
    def from_str(cls, value: str) -> "Serialization":
        return cls[value.upper()]


class Serializer:
    def serialize(self, text: str) -> bytes:
        raise NotImplementedError

    def draft_text(self, content: Any) -> str:
        """Return editor text for content loaded from a source document."""
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)


class StringSerializer(Serializer):
    def serialize(self, text: str) -> bytes:
        return text.encode("utf-8")


class JsonSerializer(Serializer):
    """Validate JSON and send it compact, keeping the key order."""

    def serialize(self, text: str) -> bytes:
        try:
            content = json.loads(text)
        except json.JSONDecodeError as ex:
            raise SerializationError(
                f"Invalid JSON: {ex.msg} (line {ex.lineno}, column {ex.colno})"
            ) from ex
        return json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def draft_text(self, content: Any) -> str:
        return json.dumps(content, ensure_ascii=False, indent=2)


class BooleanSerializer(Serializer):
    def serialize(self, text: str) -> bytes:
        value = text.strip().lower()
        if value not in {"true", "false"}:
            raise SerializationError("Expected true or false")
        return Struct(">?").pack(value == "true")


class IntegerSerializer(Serializer):
    """A big-endian signed integer of a fixed size, matching the deserializers."""

    def __init__(self, struct_format: str, label: str, bits: int) -> None:
        self._struct = Struct(struct_format)
        self._label = label
        self._minimum = -(2 ** (bits - 1))
        self._maximum = 2 ** (bits - 1) - 1

    def serialize(self, text: str) -> bytes:
        try:
            value = int(text.strip())
        except ValueError as ex:
            raise SerializationError(f"Expected {self._label}") from ex
        if not self._minimum <= value <= self._maximum:
            raise SerializationError(
                f"Expected {self._label} between {self._minimum} and {self._maximum}"
            )
        return self._struct.pack(value)


class FloatSerializer(Serializer):
    """A big-endian IEEE 754 number, matching the deserializers."""

    def __init__(self, struct_format: str, label: str) -> None:
        self._struct = Struct(struct_format)
        self._label = label

    def serialize(self, text: str) -> bytes:
        try:
            value = float(text.strip())
        except ValueError as ex:
            raise SerializationError(f"Expected {self._label}") from ex
        try:
            return self._struct.pack(value)
        except OverflowError as ex:
            raise SerializationError(f"The number is out of range for {self._label}") from ex


class BytesSerializer(Serializer):
    """Decode text written in one of Kaskade's byte encodings."""

    def __init__(self, encoding: BytesEncoding) -> None:
        self.encoding = encoding

    def serialize(self, text: str) -> bytes:
        match self.encoding:
            case BytesEncoding.BASE64:
                return self._base64(text)
            case BytesEncoding.HEX:
                return self._hex(text)
            case BytesEncoding.BYTE_ARRAY:
                return self._byte_array(text)
            case BytesEncoding.ESCAPED:
                return self._escaped(text)

    @staticmethod
    def _base64(text: str) -> bytes:
        try:
            return base64.b64decode("".join(text.split()), validate=True)
        except binascii.Error as ex:
            raise SerializationError("Invalid Base64") from ex

    @staticmethod
    def _hex(text: str) -> bytes:
        try:
            return bytes.fromhex(text)
        except ValueError as ex:
            raise SerializationError("Invalid hexadecimal bytes") from ex

    @staticmethod
    def _byte_array(text: str) -> bytes:
        try:
            values = json.loads(text) if text.strip() else []
        except json.JSONDecodeError as ex:
            raise SerializationError("Expected a JSON array of integers from 0 to 255") from ex
        if not isinstance(values, list) or not all(
            isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 255
            for value in values
        ):
            raise SerializationError("Expected a JSON array of integers from 0 to 255")
        return bytes(values)

    @staticmethod
    def _escaped(text: str) -> bytes:
        """Reverse the consumer's escaped encoding: printable ASCII, \\\\, and \\xhh."""
        data = bytearray()
        position = 0
        for match in ESCAPE_PATTERN.finditer(text):
            data.extend(BytesSerializer._ascii(text[position : match.start()]))
            escape = match.group(1)
            data.extend(b"\\" if escape == "\\" else bytes.fromhex(escape[1:]))
            position = match.end()
        data.extend(BytesSerializer._ascii(text[position:]))
        return bytes(data)

    @staticmethod
    def _ascii(text: str) -> bytes:
        if "\\" in text or not all(0x20 <= ord(character) <= 0x7E for character in text):
            raise SerializationError(
                "Escaped bytes accept printable ASCII, \\\\, and \\xhh escapes"
            )
        return text.encode("ascii")


class SerializerPool:
    def __init__(self) -> None:
        self._serializers: dict[Serialization, Serializer] = {
            Serialization.STRING: StringSerializer(),
            Serialization.BOOLEAN: BooleanSerializer(),
            Serialization.INTEGER: IntegerSerializer(">i", "a 32-bit integer", 32),
            Serialization.LONG: IntegerSerializer(">q", "a 64-bit integer", 64),
            Serialization.FLOAT: FloatSerializer(">f", "a 32-bit float"),
            Serialization.DOUBLE: FloatSerializer(">d", "a 64-bit float"),
            Serialization.JSON: JsonSerializer(),
        }
        self._bytes_serializers = {
            encoding: BytesSerializer(encoding) for encoding in BytesEncoding
        }

    def get(
        self, serialization: Serialization, encoding: BytesEncoding = BytesEncoding.BASE64
    ) -> Serializer:
        if serialization == Serialization.BYTES:
            return self._bytes_serializers[encoding]
        return self._serializers[serialization]
