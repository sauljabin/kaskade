import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from kaskade.keymaps import parse_keymap
from kaskade.timeouts import (
    ADMIN_TIMEOUT_PROPERTIES,
    CONSUMER_TIMEOUT_PROPERTIES,
    PRODUCER_TIMEOUT_PROPERTIES,
    TimeoutConfig,
    parse_timeout_seconds,
)

SETTINGS_ENV_VAR = "KASKADE_SETTINGS"
SETTINGS_FILE_NAME = "settings.yaml"
DEFAULT_ADMIN_REFRESH_INTERVAL_SECONDS = 30
MIN_ADMIN_REFRESH_INTERVAL_SECONDS = 5
ADMIN_REFRESH_INTERVAL_SETTING = "refresh-interval"
TIMEOUTS_SETTING = "timeouts"
ADMIN_SETTINGS = (ADMIN_REFRESH_INTERVAL_SETTING, TIMEOUTS_SETTING)
CONSUMER_SETTINGS = (TIMEOUTS_SETTING,)
PRODUCER_SETTINGS = (TIMEOUTS_SETTING,)


@dataclass(frozen=True)
class AppSettings:
    path: Path
    keymap: dict[str, str]
    admin_refresh_interval_seconds: int = DEFAULT_ADMIN_REFRESH_INTERVAL_SECONDS
    theme: str | None = None
    custom_themes: dict[Any, Any] = field(default_factory=dict)
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)
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
    admin, admin_warnings = _parse_section(data, "admin", ADMIN_SETTINGS)
    refresh_interval, refresh_interval_warnings = _parse_admin_refresh_interval(admin)
    admin_timeouts, admin_timeout_warnings = _parse_timeouts(
        "admin", admin, ADMIN_TIMEOUT_PROPERTIES
    )
    consumer, consumer_warnings = _parse_section(data, "consumer", CONSUMER_SETTINGS)
    consumer_timeouts, consumer_timeout_warnings = _parse_timeouts(
        "consumer", consumer, CONSUMER_TIMEOUT_PROPERTIES
    )
    producer, producer_warnings = _parse_section(data, "producer", PRODUCER_SETTINGS)
    producer_timeouts, producer_timeout_warnings = _parse_timeouts(
        "producer", producer, PRODUCER_TIMEOUT_PROPERTIES
    )
    theme, theme_warnings = _parse_theme(data.get("theme"))
    custom_themes, custom_theme_warnings = _parse_custom_themes(data.get("themes"))
    return AppSettings(
        settings_path,
        keymap,
        admin_refresh_interval_seconds=refresh_interval,
        theme=theme,
        custom_themes=custom_themes,
        timeouts=TimeoutConfig.from_dict(admin_timeouts | consumer_timeouts | producer_timeouts),
        warnings=(
            *read_warnings,
            *keymap_warnings,
            *admin_warnings,
            *refresh_interval_warnings,
            *admin_timeout_warnings,
            *consumer_warnings,
            *consumer_timeout_warnings,
            *producer_warnings,
            *producer_timeout_warnings,
            *theme_warnings,
            *custom_theme_warnings,
        ),
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


def _parse_custom_themes(configured_themes: Any) -> tuple[dict[Any, Any], tuple[str, ...]]:
    """Return the raw custom theme definitions; themes.py validates each one."""
    if configured_themes is None:
        return {}, ()
    if not isinstance(configured_themes, dict):
        return {}, ("Ignoring 'themes': it must be a mapping",)
    return configured_themes, ()


def _parse_section(
    data: dict[str, Any], section_name: str, known_settings: tuple[str, ...]
) -> tuple[dict[Any, Any], tuple[str, ...]]:
    configured = data.get(section_name, {})
    if not isinstance(configured, dict):
        return {}, (f"Ignoring '{section_name}': it must be a mapping",)

    return configured, tuple(
        f"Ignoring '{section_name}.{setting_name}': {_unknown_setting_reason(setting_name)}"
        for setting_name in configured
        if setting_name not in known_settings
    )


def _unknown_setting_reason(setting_name: Any) -> str:
    if isinstance(setting_name, str) and "_" in setting_name:
        return "setting names must use hyphens, not underscores"
    return "unknown setting"


def _parse_admin_refresh_interval(admin: dict[Any, Any]) -> tuple[int, tuple[str, ...]]:
    refresh_interval = DEFAULT_ADMIN_REFRESH_INTERVAL_SECONDS
    if ADMIN_REFRESH_INTERVAL_SETTING not in admin:
        return refresh_interval, ()

    configured_interval = admin[ADMIN_REFRESH_INTERVAL_SETTING]
    if not isinstance(configured_interval, int) or isinstance(configured_interval, bool):
        return refresh_interval, (
            f"Ignoring 'admin.{ADMIN_REFRESH_INTERVAL_SETTING}': it must be an integer",
        )
    if not is_valid_admin_refresh_interval(configured_interval):
        return refresh_interval, (
            (
                f"Ignoring 'admin.{ADMIN_REFRESH_INTERVAL_SETTING}': it must be 0 or at least "
                f"{MIN_ADMIN_REFRESH_INTERVAL_SECONDS}"
            ),
        )
    return configured_interval, ()


def _parse_timeouts(
    section_name: str, section: dict[Any, Any], properties: tuple[str, ...]
) -> tuple[dict[str, float], tuple[str, ...]]:
    """Map `<section>.timeouts.<name>` to the `<section>.<name>` --timeout property."""
    if TIMEOUTS_SETTING not in section:
        return {}, ()

    path = f"{section_name}.{TIMEOUTS_SETTING}"
    configured = section[TIMEOUTS_SETTING]
    if not isinstance(configured, dict):
        return {}, (f"Ignoring '{path}': it must be a mapping",)

    property_names = {
        property_name.partition(".")[2]: property_name for property_name in properties
    }
    timeouts: dict[str, float] = {}
    warning_messages: list[str] = []
    for name, value in configured.items():
        if name not in property_names:
            warning_messages.append(f"Ignoring '{path}.{name}': unknown setting")
        elif _is_timeout_seconds(property_names[name], value):
            timeouts[property_names[name]] = float(value)
        else:
            warning_messages.append(
                f"Ignoring '{path}.{name}': it must be a number of seconds greater than zero"
            )
    return timeouts, tuple(warning_messages)


def _is_timeout_seconds(property_name: str, value: Any) -> bool:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    try:
        parse_timeout_seconds(property_name, value)
    except ValueError:
        return False
    return True
