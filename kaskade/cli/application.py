from collections.abc import Mapping
from dataclasses import replace

from click import BadParameter

from kaskade.settings import AppSettings, load_settings
from kaskade.timeouts import TIMEOUT_PROPERTIES, TimeoutConfig


def resolve_app_settings(
    timeout_properties: tuple[str, ...],
    timeout_config: Mapping[str, str],
    *,
    theme: str | None = None,
    refresh_interval: int | None = None,
) -> AppSettings:
    """Load settings.yaml once and apply this session's command-line overrides."""
    settings = load_settings()
    return replace(
        settings,
        theme=settings.theme if theme is None else theme,
        admin_refresh_interval_seconds=(
            settings.admin_refresh_interval_seconds
            if refresh_interval is None
            else refresh_interval
        ),
        timeouts=resolve_timeouts(timeout_properties, settings.timeouts, timeout_config),
    )


def resolve_timeouts(
    properties: tuple[str, ...],
    configured: TimeoutConfig,
    inline_config: Mapping[str, str],
) -> TimeoutConfig:
    """Apply --timeout values for this command over the settings.yaml timeouts."""
    for property_name in inline_config:
        if property_name in TIMEOUT_PROPERTIES and property_name not in properties:
            raise BadParameter(
                message=(
                    f"{property_name} applies only to {property_name.partition('.')[0]}. "
                    f"Properties: {', '.join(properties)}."
                ),
                param_hint="'--timeout'",
            )

    try:
        return TimeoutConfig.from_dict({**configured.as_dict(), **inline_config})
    except ValueError as ex:
        raise BadParameter(message=str(ex), param_hint="'--timeout'") from ex
