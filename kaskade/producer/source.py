"""The record draft loaded from a --source JSON file."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DOCUMENT_FIELDS = frozenset({"headers", "key", "value"})
HEADER_FIELDS = frozenset({"key", "value"})
FIELD_PROPERTIES = frozenset({"content"})


class SourceError(ValueError):
    """An unreadable source file or invalid record document."""


@dataclass(frozen=True)
class DraftField:
    """Key or Value content from a document; None is null, distinct from ""."""

    content: Any = None
    is_null: bool = True


@dataclass(frozen=True)
class RecordDraft:
    headers: tuple[tuple[str, str | None], ...] = ()
    key: DraftField = DraftField()
    value: DraftField = DraftField()


def load_draft(path: str | Path) -> RecordDraft:
    """Read one record document; the file is never modified."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as ex:
        raise SourceError(f"Unable to read the source file: {ex}") from ex
    try:
        document = json.loads(text)
    except json.JSONDecodeError as ex:
        raise SourceError(f"Invalid JSON at line {ex.lineno}: {ex.msg}") from ex
    return _parse_document(document)


def _parse_document(document: Any) -> RecordDraft:
    if not isinstance(document, dict):
        raise SourceError("a record document must be a JSON object")
    _reject_unknown(document, DOCUMENT_FIELDS, "record")
    return RecordDraft(
        headers=_parse_headers(document.get("headers", [])),
        key=_parse_field(document.get("key"), "key"),
        value=_parse_field(document.get("value"), "value"),
    )


def _parse_headers(headers: Any) -> tuple[tuple[str, str | None], ...]:
    if not isinstance(headers, list):
        raise SourceError("'headers' must be an array")
    parsed: list[tuple[str, str | None]] = []
    for index, header in enumerate(headers):
        if not isinstance(header, dict) or set(header) != HEADER_FIELDS:
            raise SourceError(f"header {index} must be an object with 'key' and 'value'")
        name, value = header["key"], header["value"]
        if not isinstance(name, str) or not (value is None or isinstance(value, str)):
            raise SourceError(f"header {index} needs a string key and a string or null value")
        parsed.append((name, value))
    return tuple(parsed)


def _parse_field(field: Any, name: str) -> DraftField:
    if field is None:
        return DraftField()
    if not isinstance(field, dict):
        raise SourceError(f"'{name}' must be an object with 'content'")
    _reject_unknown(field, FIELD_PROPERTIES, f"'{name}'")
    content = field.get("content")
    return DraftField(content=content, is_null=content is None)


def _reject_unknown(document: dict[str, Any], allowed: frozenset[str], subject: str) -> None:
    unknown = sorted(set(document) - allowed)
    if unknown:
        raise SourceError(f"unknown {subject} field(s): {', '.join(unknown)}")
