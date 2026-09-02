from pathlib import Path
from typing import Any

from textual.keys import KEY_NAME_REPLACEMENTS, KEY_TO_UNICODE_NAME, Keys, key_to_character

NAVIGATION_BINDING_IDS = frozenset(
    {
        "kaskade.navigation.down",
        "kaskade.navigation.end",
        "kaskade.navigation.first",
        "kaskade.navigation.home",
        "kaskade.navigation.last",
        "kaskade.navigation.left",
        "kaskade.navigation.page-down",
        "kaskade.navigation.page-left",
        "kaskade.navigation.page-right",
        "kaskade.navigation.page-up",
        "kaskade.navigation.right",
        "kaskade.navigation.select",
        "kaskade.navigation.up",
    }
)

KNOWN_BINDING_IDS = (
    frozenset(
        {
            "app.command-palette",
            "app.quit",
            "help.toggle",
            "kaskade.help.close",
            "kaskade.chunk-size.close",
            "kaskade.chunk-size.select",
            "kaskade.create-topic.close",
            "kaskade.create-topic.save",
            "kaskade.delete-topic.cancel",
            "kaskade.delete-topic.confirm",
            "kaskade.describe-topic.close",
            "kaskade.edit-topic.close",
            "kaskade.edit-topic.save",
            "kaskade.filter-records.close",
            "kaskade.filter-records.apply",
            "kaskade.filter-topics.close",
            "kaskade.filter-topics.apply",
            "kaskade.record-details.close",
            "kaskade.record-details.next",
            "kaskade.record-details.previous",
            "kaskade.records.chunk-size",
            "kaskade.records.consume",
            "kaskade.records.copy",
            "kaskade.records.export",
            "kaskade.records.filter",
            "kaskade.records.show",
            "kaskade.records.show-all",
            "kaskade.topics.create",
            "kaskade.topics.copy",
            "kaskade.topics.delete",
            "kaskade.topics.describe",
            "kaskade.topics.edit",
            "kaskade.topics.filter",
            "kaskade.topics.refresh",
            "kaskade.topics.show-all",
        }
    )
    | NAVIGATION_BINDING_IDS
)

_MODIFIERS = frozenset({"alt", "ctrl", "meta", "shift", "super"})
_NAMED_KEYS = (
    {key.value for key in Keys} | set(KEY_TO_UNICODE_NAME) | set(KEY_NAME_REPLACEMENTS.values())
)


def parse_keymap(
    configured_keymap: Any, settings_path: Path
) -> tuple[dict[str, str], tuple[str, ...]]:
    warning_messages: list[str] = []
    if not isinstance(configured_keymap, dict):
        warning_messages.append(f"Ignoring {settings_path}: 'keymap' must be a mapping")
        configured_keymap = {}

    keymap: dict[str, str] = {}
    for binding_id, keys in configured_keymap.items():
        if not isinstance(binding_id, str) or binding_id not in KNOWN_BINDING_IDS:
            warning_messages.append(f"Ignoring unknown binding ID: {binding_id!r}")
            continue
        if not isinstance(keys, str) or not keys.strip():
            warning_messages.append(f"Ignoring {binding_id!r}: keys must be a non-empty string")
            continue
        invalid_keys = [key for key in keys.split(",") if not _is_valid_key(key.strip())]
        if invalid_keys:
            warning_messages.append(
                f"Ignoring {binding_id!r}: invalid key name(s) {', '.join(invalid_keys)}"
            )
            continue
        keymap[binding_id] = keys
    return keymap, tuple(warning_messages)


def _is_valid_key(key: str) -> bool:
    if not key:
        return False
    if key in _NAMED_KEYS or (len(key) == 1 and key.isprintable()):
        return True
    if key_to_character(key) is not None:
        return True

    parts = key.split("+")
    if len(parts) < 2 or any(modifier not in _MODIFIERS for modifier in parts[:-1]):
        return False
    base_key = parts[-1]
    return (
        base_key in _NAMED_KEYS
        or (len(base_key) == 1 and base_key.isprintable())
        or key_to_character(base_key) is not None
    )
