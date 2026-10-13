"""JSON highlighting for the composer, in the colors the consumer uses for record content."""

from functools import cache

import tree_sitter_json
from rich.default_styles import DEFAULT_STYLES
from rich.style import Style
from textual.app import App
from textual.widgets.text_area import TextAreaTheme
from tree_sitter import Language

from kaskade.app import KaskadeApp
from kaskade.deserializers import BytesEncoding
from kaskade.serializers import Serialization

JSON_LANGUAGE = "json"
# Captures use Rich's JSON style names, so the editor and the consumer share colors.
JSON_HIGHLIGHT_QUERY = """
(pair key: (string) @json.key)
(pair value: (string) @json.str)
(array (string) @json.str)
(document (string) @json.str)
(number) @json.number
(true) @json.bool_true
(false) @json.bool_false
(null) @json.null
["[" "]" "{" "}"] @json.brace
"""
JSON_STYLE_NAMES = (
    "json.brace",
    "json.key",
    "json.str",
    "json.number",
    "json.bool_true",
    "json.bool_false",
    "json.null",
)
JSON_INPUT_SERIALIZATIONS = frozenset(
    {
        Serialization.JSON,
        Serialization.BOOLEAN,
        Serialization.INTEGER,
        Serialization.LONG,
        Serialization.FLOAT,
        Serialization.DOUBLE,
    }
)


@cache
def json_language() -> Language:
    return Language(tree_sitter_json.language())


def highlights_json(serialization: Serialization, encoding: BytesEncoding) -> bool:
    """Whether the editor input for this serializer is JSON."""
    if serialization == Serialization.BYTES:
        return encoding == BytesEncoding.BYTE_ARRAY
    return serialization in JSON_INPUT_SERIALIZATIONS


def json_theme(app: App) -> TextAreaTheme:
    """Syntax colors for the active theme; the editor keeps its own background."""
    semantic_styles = app.semantic_styles() if isinstance(app, KaskadeApp) else {}
    syntax_styles = {}
    for name in JSON_STYLE_NAMES:
        definition = semantic_styles.get(name)
        syntax_styles[name] = (
            Style.parse(definition) if definition is not None else DEFAULT_STYLES[name]
        )
    return TextAreaTheme(name=f"kaskade-json-{app.theme}", syntax_styles=syntax_styles)
