import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from kaskade.keymaps import parse_keymap

SETTINGS_ENV_VAR = "KASKADE_SETTINGS"
SETTINGS_FILE_NAME = "settings.yaml"
DEFAULT_ADMIN_REFRESH_INTERVAL_SECONDS = 30
MIN_ADMIN_REFRESH_INTERVAL_SECONDS = 5


@dataclass(frozen=True)
class AppSettings:
    path: Path
    keymap: dict[str, str]
    admin_refresh_interval_seconds: int = DEFAULT_ADMIN_REFRESH_INTERVAL_SECONDS
    theme: str | None = None
    warnings: tuple[str, ...] = ()


def default_settings_path(
    environ: Mapping[str, str] | None = None, home: Path | None = None
) -> Path:
    """Return Kaskade's settings path on Linux and macOS."""
    environment = os.environ if environ is None else environ

    if configured_path := environment.get(SETTINGS_ENV_VAR):
        return Path(configured_path).expanduser()

    home_path = Path.home() if home is None else home
    config_home = environment.get("XDG_CONFIG_HOME")
    base_path = Path(config_home).expanduser() if config_home else home_path / ".config"
    return base_path / "kaskade" / SETTINGS_FILE_NAME


def load_settings(path: Path | None = None) -> AppSettings:
    """Load valid application settings without making startup fragile."""
    settings_path = default_settings_path() if path is None else path
    data, read_warnings = _read_settings(settings_path)
    keymap, keymap_warnings = parse_keymap(data.get("keymap", {}), settings_path)
    refresh_interval, admin_warnings = _parse_admin_settings(data.get("admin", {}))
    theme, theme_warnings = _parse_theme(data.get("theme"))
    return AppSettings(
        settings_path,
        keymap,
        admin_refresh_interval_seconds=refresh_interval,
        theme=theme,
        warnings=(*read_warnings, *keymap_warnings, *admin_warnings, *theme_warnings),
    )


def is_valid_admin_refresh_interval(value: int) -> bool:
    return value == 0 or value >= MIN_ADMIN_REFRESH_INTERVAL_SECONDS


def _read_settings(settings_path: Path) -> tuple[dict[str, Any], tuple[str, ...]]:
    if not settings_path.exists():
        return {}, ()

    try:
        data = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as ex:
        return {}, (f"Could not read {settings_path}: {ex}",)

    if data is None:
        return {}, ()
    if not isinstance(data, dict):
        return {}, (f"Ignoring {settings_path}: the document must be a mapping",)
    return data, ()


def _parse_theme(configured_theme: Any) -> tuple[str | None, tuple[str, ...]]:
    if configured_theme is None:
        return None, ()
    if not isinstance(configured_theme, str) or not configured_theme.strip():
        return None, ("Ignoring 'theme': it must be a non-empty string",)
    return configured_theme, ()


def _parse_admin_settings(configured_admin: Any) -> tuple[int, tuple[str, ...]]:
    refresh_interval = DEFAULT_ADMIN_REFRESH_INTERVAL_SECONDS
    warning_messages: list[str] = []
    if not isinstance(configured_admin, dict):
        warning_messages.append("Ignoring 'admin': it must be a mapping")
    elif "refresh_interval_seconds" in configured_admin:
        configured_interval = configured_admin["refresh_interval_seconds"]
        if not isinstance(configured_interval, int) or isinstance(configured_interval, bool):
            warning_messages.append(
                "Ignoring 'admin.refresh_interval_seconds': it must be an integer"
            )
        elif not is_valid_admin_refresh_interval(configured_interval):
            warning_messages.append(
                "Ignoring 'admin.refresh_interval_seconds': it must be 0 or at least "
                f"{MIN_ADMIN_REFRESH_INTERVAL_SECONDS}"
            )
        else:
            refresh_interval = configured_interval
    return refresh_interval, tuple(warning_messages)
