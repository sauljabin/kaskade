import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

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
    admin_refresh_interval_seconds: int = DEFAULT_ADMIN_REFRESH_INTERVAL_SECONDS
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
    """Load valid application settings without making startup fragile."""
    config_path = default_config_path() if path is None else path
    if not config_path.exists():
        return KeymapSettings(config_path, {})

    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as ex:
        return KeymapSettings(
            config_path,
            {},
            warnings=(f"Could not read {config_path}: {ex}",),
        )

    if data is None:
        return KeymapSettings(config_path, {})
    if not isinstance(data, dict):
        return KeymapSettings(
            config_path,
            {},
            warnings=(f"Ignoring {config_path}: the document must be a mapping.",),
        )

    configured_keymap = data.get("keymap", {})
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

    refresh_interval = DEFAULT_ADMIN_REFRESH_INTERVAL_SECONDS
    configured_admin = data.get("admin", {})
    if not isinstance(configured_admin, dict):
        warning_messages.append("Ignoring 'admin': it must be a mapping.")
    elif "refresh_interval_seconds" in configured_admin:
        configured_interval = configured_admin["refresh_interval_seconds"]
        if not isinstance(configured_interval, int) or isinstance(configured_interval, bool):
            warning_messages.append(
                "Ignoring 'admin.refresh_interval_seconds': it must be an integer."
            )
        elif configured_interval != 0 and configured_interval < MIN_ADMIN_REFRESH_INTERVAL_SECONDS:
            warning_messages.append(
                "Ignoring 'admin.refresh_interval_seconds': it must be 0 or at least "
                f"{MIN_ADMIN_REFRESH_INTERVAL_SECONDS}."
            )
        else:
            refresh_interval = configured_interval

    return KeymapSettings(
        config_path,
        keymap,
        admin_refresh_interval_seconds=refresh_interval,
        warnings=tuple(warning_messages),
    )


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
