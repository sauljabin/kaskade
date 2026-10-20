"""Avro schemas from local files or Registry content, with named-type references."""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from fastavro import parse_schema
from fastavro.repository.base import SchemaRepositoryError
from fastavro.schema import SchemaParseException, load_schema

from kaskade.schemas.errors import SchemaError

AVRO_SCHEMA_EXCEPTIONS = (
    json.JSONDecodeError,
    SchemaParseException,
    SchemaRepositoryError,
    TypeError,
    ValueError,
)


def parse_avro_schema(content: str, references: Iterable[str] = ()) -> Any:
    """Parse Registry content after its references, given in dependency order."""
    named_schemas: dict[str, Any] = {}
    try:
        for reference in references:
            parse_schema(json.loads(reference), named_schemas=named_schemas)
        return parse_schema(json.loads(content), named_schemas=named_schemas)
    except AVRO_SCHEMA_EXCEPTIONS as ex:
        raise SchemaError(f"Invalid Avro schema: {ex}") from ex


def load_avro_schema(path: str | Path) -> Any:
    """Read an .avsc file; fastavro loads named types from files next to it."""
    try:
        return load_schema(str(Path(path).expanduser()))
    except OSError as ex:
        raise SchemaError(f"Unable to read {path}: {ex}") from ex
    except AVRO_SCHEMA_EXCEPTIONS as ex:
        raise SchemaError(f"Invalid Avro schema in {path}: {ex}") from ex
