"""Avro binary encoding of the JSON content the consumer shows for Avro records.

The consumer renders Avro values that JSON lacks with ``str()``: timestamps,
dates, times, decimals, and nested bytes. This module reads those forms back,
guided by the schema, so a copied record produces the same Avro data.
"""

import ast
from collections.abc import Callable
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from fastavro import schemaless_writer
from fastavro.validation import ValidationError, validate

from kaskade.serializers.base import SerializationError

DATETIME_LOGICAL_TYPES = frozenset(
    {
        "timestamp-millis",
        "timestamp-micros",
        "timestamp-nanos",
        "local-timestamp-millis",
        "local-timestamp-micros",
        "local-timestamp-nanos",
    }
)
TIME_LOGICAL_TYPES = frozenset({"time-millis", "time-micros"})
INTEGER_TYPES = frozenset({"int", "long"})
NUMBER_TYPES = frozenset({"float", "double"})
RECORD_TYPES = frozenset({"record", "error"})


def encode_avro(schema: Any, content: Any) -> bytes:
    """Write `content` as Avro binary, raising errors that name paths, never values."""
    datum = to_avro(schema, content)
    try:
        validate(datum, schema, raise_errors=True)
    except ValidationError as ex:
        raise SerializationError(_mismatch(ex)) from None
    output = BytesIO()
    try:
        schemaless_writer(output, schema, datum)
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError):
        raise SerializationError("Doesn't match the Avro schema") from None
    return output.getvalue()


def to_avro(schema: Any, value: Any) -> Any:
    """Convert JSON content to the Python values fastavro writes for `schema`."""
    named = schema.get("__named_schemas", {}) if isinstance(schema, dict) else {}
    return _convert(schema, value, named)


def _resolve(schema: Any, named: dict[str, Any]) -> Any:
    """Follow named-type references and wrapped types to the schema that applies."""
    while True:
        if isinstance(schema, str) and schema in named:
            schema = named[schema]
        elif isinstance(schema, dict) and "logicalType" not in schema and _wraps(schema, named):
            schema = schema["type"]
        else:
            return schema


def _wraps(schema: dict[str, Any], named: dict[str, Any]) -> bool:
    inner = schema.get("type")
    return isinstance(inner, (dict, list)) or (isinstance(inner, str) and inner in named)


def _type_name(schema: Any) -> str:
    if isinstance(schema, str):
        return schema
    if isinstance(schema, list):
        return "union"
    return str(schema.get("type"))


def _convert(schema: Any, value: Any, named: dict[str, Any]) -> Any:
    schema = _resolve(schema, named)
    if isinstance(schema, list):
        return _convert_union(schema, value, named)
    if isinstance(schema, dict) and "logicalType" in schema:
        value = _logical(schema, value)
    type_name = _type_name(schema)
    if type_name in RECORD_TYPES and isinstance(value, dict):
        fields = {field["name"]: field["type"] for field in schema["fields"]}
        return {
            name: _convert(fields[name], item, named) if name in fields else item
            for name, item in value.items()
        }
    if type_name == "array" and isinstance(value, list):
        return [_convert(schema["items"], item, named) for item in value]
    if type_name == "map" and isinstance(value, dict):
        return {key: _convert(schema["values"], item, named) for key, item in value.items()}
    if type_name in {"bytes", "fixed"} and isinstance(value, str):
        return _bytes_literal(value)
    return value


def _convert_union(branches: list[Any], value: Any, named: dict[str, Any]) -> Any:
    """Pick the first branch the value fits, as fastavro does when writing."""
    for branch in branches:
        candidate = _convert(branch, value, named)
        if _fits(_resolve(branch, named), candidate):
            return candidate
    return value


def _fits(schema: Any, value: Any) -> bool:
    """A shallow type check for choosing a union branch; validation checks the rest."""
    logical = isinstance(schema, dict) and "logicalType" in schema
    if logical and isinstance(value, (date, time, Decimal)):
        return True
    type_name = _type_name(schema)
    if type_name == "enum":
        return value in schema["symbols"]
    if type_name in RECORD_TYPES:
        return _fits_record(schema, value)
    check = TYPE_CHECKS.get(type_name)
    return check is not None and check(value)


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_null(value: Any) -> bool:
    return value is None


def _instance_check(*types: type) -> Callable[[Any], bool]:
    def check(value: Any) -> bool:
        return isinstance(value, types)

    return check


TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "null": _is_null,
    "boolean": _instance_check(bool),
    "int": _is_integer,
    "long": _is_integer,
    "float": _is_number,
    "double": _is_number,
    "string": _instance_check(str),
    "bytes": _instance_check(bytes),
    "fixed": _instance_check(bytes),
    "array": _instance_check(list),
    "map": _instance_check(dict),
}


def _fits_record(schema: dict[str, Any], value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    names = {field["name"] for field in schema["fields"]}
    required = {field["name"] for field in schema["fields"] if "default" not in field}
    return set(value) <= names and required <= set(value)


def _logical(schema: dict[str, Any], value: Any) -> Any:
    """Read the str() forms the consumer shows; anything else is left to validation."""
    logical = schema["logicalType"]
    try:
        if logical in DATETIME_LOGICAL_TYPES and isinstance(value, str):
            return datetime.fromisoformat(_utc_suffix(value))
        if logical == "date" and isinstance(value, str):
            return date.fromisoformat(value)
        if logical in TIME_LOGICAL_TYPES and isinstance(value, str):
            return time.fromisoformat(value)
        if logical == "decimal" and (isinstance(value, str) or _is_number(value)):
            return Decimal(str(value))
    except (InvalidOperation, ValueError):
        pass
    return value


def _utc_suffix(value: str) -> str:
    """fromisoformat reads the Z suffix only in uppercase."""
    return value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value


def _bytes_literal(value: str) -> Any:
    """Read a Python bytes literal, such as b'\\x00', which the consumer shows for bytes."""
    if not value.startswith(("b'", 'b"')):
        return value
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return value
    return parsed if isinstance(parsed, bytes) else value


def _mismatch(error: ValidationError) -> str:
    """Report the deepest mismatch; a union reports every branch it tried there."""
    if not error.errors:
        return "Doesn't match the Avro schema"
    field = error.errors[-1].field
    expected = " or ".join(
        _expected(details.schema) for details in error.errors if details.field == field
    )
    return f"Doesn't match the Avro schema at {field or 'the root'}: expected {expected}"


def _expected(schema: Any) -> str:
    if isinstance(schema, dict):
        logical = schema.get("logicalType")
        name = schema.get("name")
        type_name = _type_name(schema)
        if logical is not None:
            return f"{type_name} ({logical})"
        return f"{type_name} {name}" if name else type_name
    if isinstance(schema, list):
        return " or ".join(_expected(branch) for branch in schema)
    return str(schema)
