import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from textual.keys import KEY_NAME_REPLACEMENTS, KEY_TO_UNICODE_NAME, Keys, key_to_character

CONFIG_ENV_VAR = "KASKADE_CONFIG"
CONFIG_FILE_NAME = "config.yaml"
DEFAULT_ADMIN_REFRESH_INTERVAL_SECONDS = 30
MIN_ADMIN_REFRESH_INTERVAL_SECONDS = 5

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


@dataclass(frozen=True)
class AppSettings:
    path: Path
    keymap: dict[str, str]
    admin_refresh_interval_seconds: int = DEFAULT_ADMIN_REFRESH_INTERVAL_SECONDS
    warnings: tuple[str, ...] = ()


# Compatibility name retained for callers that imported the original settings type.
KeymapSettings = AppSettings


def default_config_path(environ: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    """Return Kaskade's config path on Linux and macOS."""
    environment = os.environ if environ is None else environ

    if configured_path := environment.get(CONFIG_ENV_VAR):
        return Path(configured_path).expanduser()

    home_path = Path.home() if home is None else home
    config_home = environment.get("XDG_CONFIG_HOME")
    base_path = Path(config_home).expanduser() if config_home else home_path / ".config"
    return base_path / "kaskade" / CONFIG_FILE_NAME


def load_settings(path: Path | None = None) -> AppSettings:
    """Load valid application settings without making startup fragile."""
    config_path = default_config_path() if path is None else path
    data, read_warnings = _read_config(config_path)
    keymap, keymap_warnings = _parse_keymap(data.get("keymap", {}), config_path)
    refresh_interval, admin_warnings = _parse_admin_settings(data.get("admin", {}))
    return AppSettings(
        config_path,
        keymap,
        admin_refresh_interval_seconds=refresh_interval,
        warnings=(*read_warnings, *keymap_warnings, *admin_warnings),
    )


def load_keymap(path: Path | None = None) -> AppSettings:
    """Compatibility wrapper for the original application settings loader."""
    return load_settings(path)


def is_valid_admin_refresh_interval(value: int) -> bool:
    return value == 0 or value >= MIN_ADMIN_REFRESH_INTERVAL_SECONDS


def _read_config(config_path: Path) -> tuple[dict[str, Any], tuple[str, ...]]:
    if not config_path.exists():
        return {}, ()

    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as ex:
        return {}, (f"Could not read {config_path}: {ex}",)

    if data is None:
        return {}, ()
    if not isinstance(data, dict):
        return {}, (f"Ignoring {config_path}: the document must be a mapping.",)
    return data, ()


def _parse_keymap(
    configured_keymap: Any, config_path: Path
) -> tuple[dict[str, str], tuple[str, ...]]:
    warning_messages: list[str] = []
    if not isinstance(configured_keymap, dict):
        warning_messages.append(f"Ignoring {config_path}: 'keymap' must be a mapping.")
        configured_keymap = {}

    keymap: dict[str, str] = {}
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
    return keymap, tuple(warning_messages)


def _parse_admin_settings(configured_admin: Any) -> tuple[int, tuple[str, ...]]:
    refresh_interval = DEFAULT_ADMIN_REFRESH_INTERVAL_SECONDS
    warning_messages: list[str] = []
    if not isinstance(configured_admin, dict):
        warning_messages.append("Ignoring 'admin': it must be a mapping.")
    elif "refresh_interval_seconds" in configured_admin:
        configured_interval = configured_admin["refresh_interval_seconds"]
        if not isinstance(configured_interval, int) or isinstance(configured_interval, bool):
            warning_messages.append(
                "Ignoring 'admin.refresh_interval_seconds': it must be an integer."
            )
        elif not is_valid_admin_refresh_interval(configured_interval):
            warning_messages.append(
                "Ignoring 'admin.refresh_interval_seconds': it must be 0 or at least "
                f"{MIN_ADMIN_REFRESH_INTERVAL_SECONDS}."
            )
        else:
            refresh_interval = configured_interval
    return refresh_interval, tuple(warning_messages)


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
