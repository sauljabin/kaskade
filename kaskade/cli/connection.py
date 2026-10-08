from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from click import BadParameter, ClickException, MissingParameter

from kaskade import logger
from kaskade.authentication import (
    AwsMskAuthenticationError,
    configure_aws_msk_iam,
    validate_aws_msk_credentials,
)
from kaskade.configs import AWS_CONFIGS, BOOTSTRAP_SERVERS
from kaskade.files import load_ini

CONFIG_FILE_SECTIONS = ("kafka", "registry", "aws", "timeouts")
BOOTSTRAP_SERVERS_REQUIRED = (
    "Bootstrap servers are required. Use -b/--bootstrap-servers or set "
    "bootstrap.servers with --kafka or --config-file."
)

ConfigFile = dict[str, dict[str, str]]


@dataclass(frozen=True)
class Connection:
    """Kafka and Registry client configuration resolved from the file and the CLI."""

    kafka_config: dict[str, Any]
    registry_config: dict[str, str]


def load_config_file(config_file: str | None) -> ConfigFile:
    if config_file is None:
        return {}

    try:
        config = load_ini(config_file)
    except (OSError, ValueError) as ex:
        raise ClickException(f"Invalid configuration file: {ex}") from ex

    unknown_sections = [section for section in config if section not in CONFIG_FILE_SECTIONS]
    if unknown_sections:
        raise ClickException(f"Unknown configuration sections: {', '.join(unknown_sections)}")
    if not config:
        expected = " or ".join(f"[{section}]" for section in CONFIG_FILE_SECTIONS)
        raise ClickException(f"Configuration file requires {expected}")

    return config


def resolve_kafka_config(
    bootstrap_servers: str | None,
    file_config: Mapping[str, str],
    kafka_config: Mapping[str, Any],
) -> dict[str, Any]:
    resolved_config = {**file_config, **kafka_config}

    if bootstrap_servers is not None:
        resolved_config[BOOTSTRAP_SERVERS] = bootstrap_servers

    resolved_bootstrap_servers = resolved_config.get(BOOTSTRAP_SERVERS)
    if not isinstance(resolved_bootstrap_servers, str) or not resolved_bootstrap_servers.strip():
        raise ClickException(BOOTSTRAP_SERVERS_REQUIRED)

    return resolved_config


def validate_aws_config(aws_config: Mapping[str, str]) -> None:
    if not aws_config:
        return

    if [config for config in aws_config if config not in AWS_CONFIGS]:
        raise BadParameter(message=f"Valid properties: {list(AWS_CONFIGS)}.")

    if not aws_config.get("region"):
        raise MissingParameter(param_hint="'--aws region=my-region'", param_type="option")


def resolve_connection(
    file_config: ConfigFile,
    bootstrap_servers: str | None,
    kafka_config: Mapping[str, Any],
    aws_config: Mapping[str, str],
    registry_config: Mapping[str, str] | None = None,
) -> Connection:
    """Merge file and CLI properties, then enable Amazon MSK IAM when configured."""
    resolved_kafka_config = resolve_kafka_config(
        bootstrap_servers, file_config.get("kafka", {}), kafka_config
    )
    resolved_registry_config = {**file_config.get("registry", {}), **(registry_config or {})}
    resolved_aws_config = {**file_config.get("aws", {}), **aws_config}

    validate_aws_config(resolved_aws_config)
    try:
        validate_aws_msk_credentials(resolved_aws_config)
    except AwsMskAuthenticationError as ex:
        logger.error("aws msk authentication error: %s", ex)
        raise ClickException(str(ex)) from ex

    return Connection(
        kafka_config=configure_aws_msk_iam(resolved_kafka_config, resolved_aws_config),
        registry_config=resolved_registry_config,
    )
