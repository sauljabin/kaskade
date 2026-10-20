"""JSON Schema validators that never fetch remote URLs or describe record content."""

import json
from collections.abc import Iterator, Mapping
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urldefrag, urljoin, urlsplit

from jsonschema.exceptions import (  # type: ignore[import-untyped]
    SchemaError as InvalidJsonSchemaError,
)
from jsonschema.exceptions import ValidationError, best_match
from jsonschema.validators import validator_for  # type: ignore[import-untyped]
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from kaskade.schemas.errors import SchemaError

VALIDATION_FAILED = "JSON Schema validation failed"


def json_validator(schema: Any, resources: Mapping[str, Any] | None = None) -> Any:
    """Build a validator for `schema`, resolving `$ref`s only from `resources`."""
    # attrs names the field _retrieve and accepts it as retrieve, which mypy can't see.
    registry: Registry[Any] = Registry(retrieve=_refuse_retrieval)  # type: ignore[call-arg]
    for uri, contents in (resources or {}).items():
        registry = registry.with_resource(uri, _resource(contents))
    try:
        validator_class = validator_for(schema)
        validator_class.check_schema(schema)
        return validator_class(schema, registry=registry)
    except (InvalidJsonSchemaError, TypeError, ValueError) as ex:
        raise SchemaError(f"Invalid JSON Schema: {_schema_problem(ex)}") from ex


def load_json_schema(path: str | Path) -> Any:
    """Read a JSON Schema file, loading the relative `$ref` files next to it."""
    schema_path = Path(path).expanduser()
    schema = _read_json(schema_path)
    resources: dict[str, Any] = {}
    _collect_local_references(schema_path.resolve().parent, schema, "", resources)
    return json_validator(schema, resources)


def validation_error(validator: Any, content: Any) -> str | None:
    """Describe the most relevant violation by JSON path and rule, or return None."""
    try:
        error = best_match(validator.iter_errors(content))
    except Unresolvable as ex:
        raise SchemaError(f"Unresolvable JSON Schema reference: {ex.ref}") from ex
    if error is None:
        return None
    return f"{VALIDATION_FAILED}: {describe(error)}"


def describe(error: ValidationError) -> str:
    """Name the path and failed rule; the schema's values may appear, the record's never."""
    rule = error.validator
    expected = error.validator_value
    if rule is None:
        reason = "is not allowed"
    elif rule == "type":
        types = expected if isinstance(expected, list) else [expected]
        reason = f"expected type {' or '.join(str(name) for name in types)}"
    elif rule == "required" and isinstance(error.instance, dict):
        missing = [name for name in expected if name not in error.instance]
        reason = f"missing required property {', '.join(map(str, missing))}"
    elif isinstance(expected, (bool, int, float, str)):
        reason = f"fails {rule} {json.dumps(expected, ensure_ascii=False)}"
    else:
        reason = f"fails {rule}"
    return f"{error.json_path} {reason}"


def _resource(contents: Any) -> Resource[Any]:
    return Resource.from_contents(contents, default_specification=DRAFT202012)


def _refuse_retrieval(uri: str) -> Resource[Any]:
    raise SchemaError(
        f"JSON Schema reference {uri} is not available; remote URLs are never fetched"
    )


def _schema_problem(ex: Exception) -> str:
    if isinstance(ex, InvalidJsonSchemaError):
        return f"{ex.json_path} {ex.message}"
    return str(ex)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as ex:
        raise SchemaError(f"Unable to read {path}: {ex}") from ex
    except json.JSONDecodeError as ex:
        raise SchemaError(f"Invalid JSON in {path} at line {ex.lineno}: {ex.msg}") from ex


def _collect_local_references(
    directory: Path, document: Any, base: str, resources: dict[str, Any]
) -> None:
    """Load each relative `$ref` document once, resolved like the validator resolves it."""
    for reference in _references(document):
        uri = urldefrag(urljoin(base, reference)).url
        if not uri or uri in resources or urlsplit(uri).scheme:
            # Fragments are local, and absolute URIs may name an embedded `$id`;
            # the validator reports those it can't find without fetching them.
            continue
        relative = PurePosixPath(uri)
        if relative.is_absolute() or ".." in relative.parts:
            raise SchemaError(f"JSON Schema reference {uri} must stay next to the schema")
        contents = _read_json(directory.joinpath(*relative.parts))
        resources[uri] = contents
        _collect_local_references(directory, contents, uri, resources)


def _references(document: Any) -> Iterator[str]:
    if isinstance(document, dict):
        reference = document.get("$ref")
        if isinstance(reference, str):
            yield reference
        for value in document.values():
            yield from _references(value)
    elif isinstance(document, list):
        for value in document:
            yield from _references(value)
