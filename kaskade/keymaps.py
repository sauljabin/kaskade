import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml
from textual.keys import KEY_NAME_REPLACEMENTS, KEY_TO_UNICODE_NAME, Keys, key_to_character

CONFIG_ENV_VAR = "KASKADE_CONFIG"
CONFIG_FILE_NAME = "config.yaml"

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
            "kaskade.chunk-size.close",
            "kaskade.create-topic.close",
            "kaskade.create-topic.save",
            "kaskade.delete-topic.cancel",
            "kaskade.describe-topic.close",
            "kaskade.edit-topic.close",
            "kaskade.edit-topic.save",
            "kaskade.filter-records.close",
            "kaskade.filter-topics.close",
            "kaskade.record-details.close",
            "kaskade.records.chunk-size",
            "kaskade.records.consume",
            "kaskade.records.filter",
            "kaskade.records.show",
            "kaskade.records.show-all",
            "kaskade.topics.create",
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


@dataclass(frozen=True)
class KeymapSettings:
    path: Path
    keymap: dict[str, str]
    warnings: tuple[str, ...] = ()


def default_config_path(environ: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    """Return Kaskade's config path on Linux and macOS."""
    environment = os.environ if environ is None else environ

    if configured_path := environment.get(CONFIG_ENV_VAR):
        return Path(configured_path).expanduser()

    home_path = Path.home() if home is None else home
    config_home = environment.get("XDG_CONFIG_HOME")
    base_path = Path(config_home).expanduser() if config_home else home_path / ".config"
    return base_path / "kaskade" / CONFIG_FILE_NAME


def load_keymap(path: Path | None = None) -> KeymapSettings:
    """Load valid Textual binding overrides without making startup fragile."""
    config_path = default_config_path() if path is None else path
    if not config_path.exists():
        return KeymapSettings(config_path, {})

    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as ex:
        return KeymapSettings(
            config_path,
            {},
            (f"Could not read {config_path}: {ex}",),
        )

    if data is None:
        return KeymapSettings(config_path, {})
    if not isinstance(data, dict):
        return KeymapSettings(
            config_path,
            {},
            (f"Ignoring {config_path}: the document must be a mapping.",),
        )

    configured_keymap = data.get("keymap", {})
    if not isinstance(configured_keymap, dict):
        return KeymapSettings(
            config_path,
            {},
            (f"Ignoring {config_path}: 'keymap' must be a mapping.",),
        )

    keymap: dict[str, str] = {}
    warning_messages: list[str] = []
    for binding_id, keys in configured_keymap.items():
        if not isinstance(binding_id, str) or binding_id not in KNOWN_BINDING_IDS:
            warning_messages.append(f"Ignoring unknown binding ID: {binding_id!r}.")
            continue
        if not isinstance(keys, str) or not keys.strip():
            warning_messages.append(f"Ignoring {binding_id!r}: keys must be a non-empty string.")
            continue
        invalid_keys = [key for key in keys.split(",") if not _is_valid_key(key.strip())]
        if invalid_keys:
            warning_messages.append(
                f"Ignoring {binding_id!r}: invalid key name(s) {', '.join(invalid_keys)}."
            )
            continue
        keymap[binding_id] = keys

    return KeymapSettings(config_path, keymap, tuple(warning_messages))


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
