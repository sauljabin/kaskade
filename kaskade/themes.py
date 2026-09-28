import re
from collections.abc import Collection, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from textual.color import Color, ColorParseError
from textual.theme import BUILTIN_THEMES, Theme

from kaskade.settings import AppSettings, load_settings

DEFAULT_THEME = "eva01-berserk"
EVA01_THEME = Theme(
    name="eva01",
    primary="#9B4DCA",
    secondary="#A6FF4D",
    warning="#FF9D1C",
    error="#FF4D5A",
    success="#A6FF4D",
    accent="#FF7A00",
    foreground="#F3ECFF",
    background="#2A1845",
    surface="#1F0E36",
    panel="#0E0024",
    boost="#341B55",
    dark=True,
)
EVA01_BERSERK_THEME = Theme(
    name=DEFAULT_THEME,
    primary="#9B4DCA",
    secondary="#A6FF4D",
    warning="#FF9D1C",
    error="#FF4D5A",
    success="#A6FF4D",
    accent="#FF7A00",
    foreground="#F3ECFF",
    background="#0E0024",
    surface="#1C1030",
    panel="#2A1845",
    boost="#341B55",
    dark=True,
)
KASKADE_THEMES = (EVA01_THEME, EVA01_BERSERK_THEME)


CUSTOM_THEME_COLORS = (
    "primary",
    "secondary",
    "warning",
    "error",
    "success",
    "accent",
    "foreground",
    "background",
    "surface",
    "panel",
    "boost",
)
CUSTOM_THEME_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def available_theme_names() -> tuple[str, ...]:
    """Return every Textual built-in theme plus Kaskade's bundled themes."""
    return tuple(sorted((*BUILTIN_THEMES, *(theme.name for theme in KASKADE_THEMES))))


def configured_theme_names(settings_path: Path | None = None) -> tuple[str, ...]:
    """Return the available themes plus the valid custom themes in settings.yaml."""
    custom_themes, _ = parse_custom_themes(load_settings(settings_path).custom_themes)
    return tuple(sorted((*available_theme_names(), *(theme.name for theme in custom_themes))))


def parse_custom_themes(
    definitions: Mapping[Any, Any],
) -> tuple[tuple[Theme, ...], tuple[str, ...]]:
    """Build custom themes, skipping invalid definitions and properties with warnings."""
    reserved_names = set(available_theme_names())
    themes: list[Theme] = []
    warnings: list[str] = []
    for name, definition in definitions.items():
        theme, theme_warnings = _parse_custom_theme(name, definition, reserved_names)
        warnings.extend(theme_warnings)
        if theme is not None:
            themes.append(theme)
    return tuple(themes), tuple(warnings)


def _parse_custom_theme(
    name: Any, definition: Any, reserved_names: Collection[str]
) -> tuple[Theme | None, list[str]]:
    setting = f"themes.{name}"
    if not isinstance(name, str) or CUSTOM_THEME_NAME.fullmatch(name) is None:
        reason = "names use lowercase letters, digits, and single hyphens"
        return None, [f"Ignoring '{setting}': {reason}"]
    if name in reserved_names:
        return None, [f"Ignoring '{setting}': a built-in theme already uses this name"]
    if not isinstance(definition, dict):
        return None, [f"Ignoring '{setting}': it must be a mapping"]

    properties, warnings = _parse_theme_properties(setting, definition)
    if "primary" not in properties:
        warnings.append(f"Ignoring '{setting}': it needs a valid 'primary' color")
        return None, warnings
    return Theme(name=name, **properties), warnings


def _parse_theme_properties(
    setting: str, definition: dict[Any, Any]
) -> tuple[dict[str, Any], list[str]]:
    properties: dict[str, Any] = {}
    warnings: list[str] = []
    for property_name, value in definition.items():
        property_setting = f"{setting}.{property_name}"
        if property_name == "dark":
            if isinstance(value, bool):
                properties["dark"] = value
            else:
                warnings.append(f"Ignoring '{property_setting}': it must be true or false")
        elif property_name in CUSTOM_THEME_COLORS:
            color = _theme_color(value)
            if color is None:
                warnings.append(
                    f"Ignoring '{property_setting}': it must be an opaque color such as "
                    '"#268BD2"; quote hex colors in YAML'
                )
            else:
                properties[property_name] = color
        else:
            warnings.append(f"Ignoring '{property_setting}': unknown theme property")
    return properties, warnings


def _theme_color(value: Any) -> str | None:
    """Normalize a Textual color for Rich, keeping ANSI colors tied to the terminal."""
    if not isinstance(value, str):
        return None
    try:
        color = Color.parse(value)
    except ColorParseError:
        return None
    if color.ansi is not None:
        return value
    return color.hex if color.a == 1 else None


def resolve_theme(settings: AppSettings, theme_names: Collection[str]) -> AppSettings:
    configured_theme = settings.theme
    if configured_theme is None:
        return replace(settings, theme=DEFAULT_THEME)
    if configured_theme not in theme_names:
        return replace(
            settings,
            theme=DEFAULT_THEME,
            warnings=(*settings.warnings, f"Ignoring 'theme': unknown theme {configured_theme!r}"),
        )
    return settings
