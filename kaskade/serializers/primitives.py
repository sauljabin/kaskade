"""Serializers for primitive values, plain JSON, and encoded bytes."""

import base64
import binascii
import json
import re
from pathlib import Path
from struct import Struct
from typing import Any

from kaskade.deserializers import BytesEncoding
from kaskade.schemas.json_schema import validation_error
from kaskade.serializers.base import (
    JsonDocumentSerializer,
    SerializationError,
    Serializer,
    compact_json,
    parse_json,
)

ESCAPE_PATTERN = re.compile(r"\\(\\|x[0-9a-fA-F]{2})")


class StringSerializer(Serializer):
    label = "STRING"

    def serialize(self, text: str) -> bytes:
        return text.encode("utf-8")


class JsonSerializer(JsonDocumentSerializer):
    """Validate JSON, against a local JSON Schema when given, and send it compact."""

    def __init__(self, validator: Any = None, schema_path: str | None = None) -> None:
        self._validator = validator
        self.label = "JSON" if schema_path is None else f"JSON · {Path(schema_path).name}"

    def serialize(self, text: str) -> bytes:
        content = parse_json(text)
        if self._validator is not None:
            error = validation_error(self._validator, content)
            if error is not None:
                raise SerializationError(error)
        return compact_json(content)


class BooleanSerializer(Serializer):
    label = "BOOLEAN"
    edits_json = True

    def serialize(self, text: str) -> bytes:
        value = text.strip().lower()
        if value not in {"true", "false"}:
            raise SerializationError("Expected true or false")
        return Struct(">?").pack(value == "true")


class IntegerSerializer(Serializer):
    """A big-endian signed integer of a fixed size, matching the deserializers."""

    edits_json = True

    def __init__(self, struct_format: str, label: str, bits: int, name: str) -> None:
        self._struct = Struct(struct_format)
        self._label = label
        self.label = name
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

    edits_json = True

    def __init__(self, struct_format: str, label: str, name: str) -> None:
        self._struct = Struct(struct_format)
        self._label = label
        self.label = name

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
        self.label = f"BYTES · {encoding.name}"
        self.edits_json = encoding == BytesEncoding.BYTE_ARRAY

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
