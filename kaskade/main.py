import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import cloup
from click import BadParameter, ClickException, MissingParameter
from cloup.constraints import mutually_exclusive
from confluent_kafka import KafkaException

from kaskade import APP_VERSION, logger
from kaskade.admin import KaskadeAdmin
from kaskade.apicurio import APICURIO_PREFIX, ApicurioConfig, ApicurioRegistryError
from kaskade.authentication import (
    AwsMskAuthenticationError,
    configure_aws_msk_iam,
    validate_aws_msk_credentials,
)
from kaskade.cli_utils import tuple_properties_to_dict, validate_aws_config
from kaskade.configs import (
    APICURIO_OPTION,
    AUTO_OFFSET_RESET,
    AVRO_DESERIALIZER_CONFIGS,
    AWS_CONFIGS,
    BOOTSTRAP_SERVERS,
    BYTES_DESERIALIZER_CONFIGS,
    BYTES_ENCODINGS,
    CONFLUENT_OPTION,
    DESERIALIZER_FRAMINGS,
    EARLIEST,
    FALLBACK_CONFIGS,
    FRAMING_CONFIGS,
    JSON_DESERIALIZER_CONFIGS,
    PROTOBUF_DESERIALIZER_CONFIGS,
    REGISTRY_PROVIDERS,
)
from kaskade.consumer import KaskadeConsumer
from kaskade.deserializers import Deserialization
from kaskade.logs import configure_logging
from kaskade.models import PartitionOffset, PartitionSelection
from kaskade.services import PartitionSelectionError
from kaskade.settings import (
    MIN_ADMIN_REFRESH_INTERVAL_SECONDS,
    is_valid_admin_refresh_interval,
)
from kaskade.themes import available_theme_names
from kaskade.timeouts import TIMEOUT_PROPERTIES, TimeoutConfig
from kaskade.utils import load_ini

KAFKA_CONFIG_HELP = (
    "Kafka client property. Repeatable; overrides matching properties from --config-file."
)
CONFIG_FILE_HELP = (
    "INI file with [kafka], [registry], [aws], and/or [timeouts] configuration sections."
)
CONFIG_FILE_SECTIONS = ("kafka", "registry", "aws", "timeouts")
BOOTSTRAP_SERVERS_HELP = (
    "Bootstrap servers. Comma-separated host:port pairs; overrides bootstrap.servers "
    "from Kafka client configuration."
)
BOOTSTRAP_SERVERS_REQUIRED = (
    "Bootstrap servers are required. Use -b/--bootstrap-servers or set "
    "bootstrap.servers with --kafka or --config-file."
)
EPILOG_HELP = "More information at https://github.com/sauljabin/kaskade."
EARLIEST_HELP = (
    "Read all partitions from their earliest available offsets, ignoring committed "
    "consumer-group offsets."
)
PARTITION_SELECTION_METAVAR = "partition[:offset|earliest]"
PARTITION_SELECTION_SYNTAX = "<partition>[:<absolute-offset|earliest>]"
PARTITION_SELECTION_HELP = (
    "Consume only this partition, optionally from an absolute offset or its earliest "
    f"available offset. Format: {PARTITION_SELECTION_METAVAR}. Repeatable."
)
PARTITION_SELECTION_PATTERN = re.compile(
    rf"(?P<partition>[0-9]+)(?::(?P<offset>[0-9]+|{re.escape(EARLIEST)}))?"
)
AWS_CONFIG_HELP = (
    "Amazon MSK IAM property. Repeatable; overrides matching properties from "
    f"--config-file. Properties: {', '.join(AWS_CONFIGS)}."
)
TIMEOUT_CONFIG_HELP = (
    "Kaskade operation timeout in seconds. Repeatable; overrides matching properties from "
    f"--config-file. Properties: {', '.join(TIMEOUT_PROPERTIES)}."
)
THEME_HELP = (
    "Textual theme name; overrides settings.yaml. When omitted, settings.yaml or "
    "Eva01 Berserk is used."
)
AVRO_CONFIG_HELP = (
    "Avro deserializer property. Repeatable; required when the key or value format is "
    f"avro. Properties: {', '.join(AVRO_DESERIALIZER_CONFIGS)}. Framing: "
    f"{', '.join(DESERIALIZER_FRAMINGS)} (case-insensitive); scoped framing overrides "
    "the global value."
)
PROTOBUF_CONFIG_HELP = (
    "Protobuf deserializer property. Repeatable; required when the key or value format "
    f"is protobuf. Properties: {', '.join(PROTOBUF_DESERIALIZER_CONFIGS)}. Framing: "
    f"{', '.join(DESERIALIZER_FRAMINGS)} (case-insensitive); scoped framing overrides "
    "the global value."
)
JSON_CONFIG_HELP = (
    "JSON deserializer property. Repeatable. "
    f"Properties: {', '.join(JSON_DESERIALIZER_CONFIGS)}. Framing: "
    f"{', '.join(DESERIALIZER_FRAMINGS)} (case-insensitive); scoped framing overrides "
    "the global value."
)
BYTES_CONFIG_HELP = (
    "Byte presentation property for keys and values using the BYTES deserializer. "
    f"Repeatable. Properties: {', '.join(BYTES_DESERIALIZER_CONFIGS)}. Encodings: "
    f"{', '.join(BYTES_ENCODINGS)}; scoped encodings override the global value."
)
FALLBACK_CONFIG_HELP = (
    "Global byte presentation property for key, value, and header deserialization errors. "
    f"Repeatable. Properties: {', '.join(FALLBACK_CONFIGS)}. Encodings: "
    f"{', '.join(BYTES_ENCODINGS)}."
)
REGISTRY_CONFIG_HELP = (
    "Registry provider or client property. Repeatable; overrides matching properties from "
    f"--config-file. provider choices: {', '.join(REGISTRY_PROVIDERS)} (case-insensitive); "
    f"defaults to {CONFLUENT_OPTION}. Use provider={APICURIO_OPTION} with supported official "
    "Apicurio deserializer properties."
)
CliDecoratorTarget = TypeVar("CliDecoratorTarget", bound=Callable[..., Any])


def kafka_connection_options() -> Callable[[CliDecoratorTarget], CliDecoratorTarget]:
    return cloup.option_group(
        "Kafka connection options",
        cloup.option(
            "-b",
            "--bootstrap-servers",
            "bootstrap_servers",
            help=BOOTSTRAP_SERVERS_HELP,
            metavar="host:port",
        ),
        cloup.option(
            "--kafka",
            "kafka_config",
            help=KAFKA_CONFIG_HELP,
            metavar="property=value",
            multiple=True,
            callback=tuple_properties_to_dict,
        ),
    )


def configuration_options() -> Callable[[CliDecoratorTarget], CliDecoratorTarget]:
    return cloup.option_group(
        "Configuration options",
        cloup.option(
            "--config-file",
            "config_file",
            help=CONFIG_FILE_HELP,
            type=cloup.Path(exists=True, dir_okay=False),
            metavar="filename",
        ),
    )


def aws_options() -> Callable[[CliDecoratorTarget], CliDecoratorTarget]:
    return cloup.option_group(
        "AWS options",
        cloup.option(
            "--aws",
            "aws_config",
            help=AWS_CONFIG_HELP,
            metavar="property=value",
            multiple=True,
            callback=tuple_properties_to_dict,
        ),
    )


def timeout_options() -> Callable[[CliDecoratorTarget], CliDecoratorTarget]:
    return cloup.option_group(
        "Timeout options",
        cloup.option(
            "--timeout",
            "timeout_config",
            help=TIMEOUT_CONFIG_HELP,
            metavar="property=seconds",
            multiple=True,
            callback=tuple_properties_to_dict,
        ),
    )


def theme_option() -> Callable[[CliDecoratorTarget], CliDecoratorTarget]:
    return cloup.option(
        "--theme",
        type=cloup.Choice(available_theme_names(), case_sensitive=False),
        default=None,
        help=THEME_HELP,
        metavar="name",
    )


def admin_application_options() -> Callable[[CliDecoratorTarget], CliDecoratorTarget]:
    return cloup.option_group(
        "Application options",
        theme_option(),
        cloup.option(
            "--refresh-interval",
            type=int,
            callback=validate_admin_refresh_interval,
            metavar="seconds",
            help="Admin auto-refresh interval. Use 0 to disable; overrides settings.yaml.",
        ),
    )


def consumer_application_options() -> Callable[[CliDecoratorTarget], CliDecoratorTarget]:
    return cloup.option_group("Application options", theme_option())


def string_to_deserializer_type(ctx: Any, param: Any, value: Any) -> Any:
    if value not in Deserialization.str_list():
        raise BadParameter(
            message=f"Should be one of {Deserialization.str_list()}", ctx=ctx, param=param
        )

    return Deserialization.from_str(value)


def validate_admin_refresh_interval(ctx: Any, param: Any, value: int | None) -> int | None:
    if value is not None and not is_valid_admin_refresh_interval(value):
        raise BadParameter(
            message=f"Should be 0 or at least {MIN_ADMIN_REFRESH_INTERVAL_SECONDS} seconds.",
            ctx=ctx,
            param=param,
        )
    return value


def parse_partition_selections(
    ctx: Any, param: Any, value: tuple[str, ...]
) -> tuple[PartitionSelection, ...]:
    selections: list[PartitionSelection] = []
    seen: set[int] = set()

    for raw in value:
        match = PARTITION_SELECTION_PATTERN.fullmatch(raw)
        if match is None:
            raise BadParameter(
                message=(
                    f"Should be {PARTITION_SELECTION_SYNTAX} with "
                    f"non-negative numbers; got {raw!r}."
                ),
                ctx=ctx,
                param=param,
            )

        partition = int(match.group("partition"))
        if partition in seen:
            raise BadParameter(
                message=f"Partition {partition} was specified more than once.",
                ctx=ctx,
                param=param,
            )
        seen.add(partition)

        raw_offset = match.group("offset")
        offset: int | PartitionOffset | None = None
        if raw_offset == EARLIEST:
            offset = PartitionOffset.EARLIEST
        elif raw_offset is not None:
            offset = int(raw_offset)
        selections.append(PartitionSelection(partition, offset))

    return tuple(selections)


def load_config_file(config_file: str | None) -> dict[str, dict[str, str]]:
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
    file_config: dict[str, str],
    kafka_config: dict[str, Any],
) -> dict[str, Any]:
    resolved_config = file_config | kafka_config

    if bootstrap_servers is not None:
        resolved_config[BOOTSTRAP_SERVERS] = bootstrap_servers

    resolved_bootstrap_servers = resolved_config.get(BOOTSTRAP_SERVERS)
    if not isinstance(resolved_bootstrap_servers, str) or not resolved_bootstrap_servers.strip():
        raise ClickException(BOOTSTRAP_SERVERS_REQUIRED)

    return resolved_config


def resolve_timeout_config(
    file_config: dict[str, str], inline_config: dict[str, str]
) -> TimeoutConfig:
    try:
        return TimeoutConfig.from_dict(file_config | inline_config)
    except ValueError as ex:
        raise BadParameter(
            message=str(ex), param_hint="'--timeout' or the [timeouts] section"
        ) from ex


def configured_timeout_options(
    file_config: dict[str, str], inline_config: dict[str, str]
) -> dict[str, TimeoutConfig]:
    if not file_config and not inline_config:
        return {}
    return {"timeouts": resolve_timeout_config(file_config, inline_config)}


@cloup.group(epilog=EPILOG_HELP)
@cloup.version_option(APP_VERSION)
def cli() -> None:
    """kaskade is a terminal user interface for kafka."""
    configure_logging()


@cli.command(epilog=EPILOG_HELP)
@configuration_options()
@kafka_connection_options()
@aws_options()
@timeout_options()
@admin_application_options()
def admin(
    bootstrap_servers: str | None,
    config_file: str | None,
    kafka_config: dict[str, Any],
    aws_config: dict[str, str],
    timeout_config: dict[str, str],
    theme: str | None,
    refresh_interval: int | None,
) -> None:
    """
    Administrator mode.

    \b
    Examples:
      kaskade admin -b localhost:9092
      kaskade admin -b localhost:9092 --refresh-interval 10
      kaskade admin --config-file client.ini
      kaskade admin -b localhost:9092 --aws region=us-east-1
    """

    file_config = load_config_file(config_file)
    kafka_config = resolve_kafka_config(
        bootstrap_servers, file_config.get("kafka", {}), kafka_config
    )
    aws_config = file_config.get("aws", {}) | aws_config
    application_timeout_options = configured_timeout_options(
        file_config.get("timeouts", {}), timeout_config
    )
    validate_aws_config(aws_config)
    try:
        validate_aws_msk_credentials(aws_config)
    except AwsMskAuthenticationError as ex:
        logger.error("aws msk authentication error: %s", ex)
        raise ClickException(str(ex)) from ex
    kafka_config = configure_aws_msk_iam(kafka_config, aws_config)

    admin_options: dict[str, Any] = {
        "refresh_interval": refresh_interval,
        **application_timeout_options,
    }
    kaskade_app = KaskadeAdmin(kafka_config, **admin_options)
    if theme is not None:
        kaskade_app.theme = theme
    kaskade_app.run()


@cli.command(epilog=EPILOG_HELP, show_constraints=True)
@configuration_options()
@kafka_connection_options()
@aws_options()
@timeout_options()
@cloup.option_group(
    "Consumption options",
    cloup.option(
        "-t",
        "--topic",
        "topic",
        help="Topic name.",
        metavar="name",
        required=True,
    ),
    mutually_exclusive(
        cloup.option(
            "--earliest",
            "earliest",
            help=EARLIEST_HELP,
            is_flag=True,
        ),
        cloup.option(
            "--partition",
            "partitions",
            help=PARTITION_SELECTION_HELP,
            metavar=PARTITION_SELECTION_METAVAR,
            multiple=True,
            callback=parse_partition_selections,
        ),
    ),
)
@cloup.option_group(
    "Deserialization options",
    cloup.option(
        "-k",
        "--key",
        "key_deserialization",
        type=cloup.Choice(Deserialization.str_list(), False),
        help="Key deserializer (case-insensitive).",
        default=str(Deserialization.BYTES),
        show_default=True,
        callback=string_to_deserializer_type,
    ),
    cloup.option(
        "-v",
        "--value",
        "value_deserialization",
        type=cloup.Choice(Deserialization.str_list(), False),
        help="Value deserializer (case-insensitive).",
        default=str(Deserialization.BYTES),
        show_default=True,
        callback=string_to_deserializer_type,
    ),
)
@cloup.option_group(
    "Bytes options",
    cloup.option(
        "--bytes",
        "bytes_config",
        help=BYTES_CONFIG_HELP,
        metavar="property=value",
        multiple=True,
        callback=tuple_properties_to_dict,
    ),
)
@cloup.option_group(
    "Fallback options",
    cloup.option(
        "--fallback",
        "fallback_config",
        help=FALLBACK_CONFIG_HELP,
        metavar="property=value",
        multiple=True,
        callback=tuple_properties_to_dict,
    ),
)
@cloup.option_group(
    "JSON options",
    cloup.option(
        "--json",
        "json_config",
        help=JSON_CONFIG_HELP,
        metavar="property=value",
        multiple=True,
        callback=tuple_properties_to_dict,
    ),
)
@cloup.option_group(
    "Avro options",
    cloup.option(
        "--avro",
        "avro_config",
        help=AVRO_CONFIG_HELP,
        metavar="property=value",
        multiple=True,
        callback=tuple_properties_to_dict,
    ),
)
@cloup.option_group(
    "Protobuf options",
    cloup.option(
        "--protobuf",
        "protobuf_config",
        help=PROTOBUF_CONFIG_HELP,
        metavar="property=value",
        multiple=True,
        callback=tuple_properties_to_dict,
    ),
)
@cloup.option_group(
    "Schema Registry options",
    cloup.option(
        "--registry",
        "registry_config",
        help=REGISTRY_CONFIG_HELP,
        metavar="property=value",
        multiple=True,
        callback=tuple_properties_to_dict,
    ),
)
@consumer_application_options()
def consumer(
    bootstrap_servers: str | None,
    kafka_config: dict[str, Any],
    registry_config: dict[str, str],
    protobuf_config: dict[str, str],
    avro_config: dict[str, str],
    json_config: dict[str, str],
    bytes_config: dict[str, str],
    fallback_config: dict[str, str],
    topic: str,
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
    earliest: bool,
    partitions: tuple[PartitionSelection, ...],
    config_file: str | None,
    aws_config: dict[str, str],
    timeout_config: dict[str, str],
    theme: str | None,
) -> None:
    """
    Consumer mode.

    \b
    Examples:
      kaskade consumer -b localhost:9092 -t my-topic
      kaskade consumer -b localhost:9092 -t my-topic --earliest -k string -v json
      kaskade consumer -b localhost:9092 -t my-topic -k string --bytes encoding=hex --fallback encoding=escaped
      kaskade consumer -b localhost:9092 -t my-topic -v registry --registry url=http://localhost:8081
    """

    file_config = load_config_file(config_file)
    kafka_config = resolve_kafka_config(
        bootstrap_servers, file_config.get("kafka", {}), kafka_config
    )
    registry_config = file_config.get("registry", {}) | registry_config
    aws_config = file_config.get("aws", {}) | aws_config
    application_timeout_options = configured_timeout_options(
        file_config.get("timeouts", {}), timeout_config
    )
    validate_aws_config(aws_config)
    try:
        validate_aws_msk_credentials(aws_config)
    except AwsMskAuthenticationError as ex:
        logger.error("aws msk authentication error: %s", ex)
        raise ClickException(str(ex)) from ex
    kafka_config = configure_aws_msk_iam(kafka_config, aws_config)

    if earliest:
        kafka_config[AUTO_OFFSET_RESET] = EARLIEST

    validate_deserializer(
        registry_config, avro_config, protobuf_config, key_deserialization, value_deserialization
    )
    validate_schema_registry_usage(registry_config, key_deserialization, value_deserialization)
    validate_registry_config(registry_config)
    validate_bytes(bytes_config, key_deserialization, value_deserialization)
    validate_fallback(fallback_config)
    validate_json(json_config, key_deserialization, value_deserialization)
    validate_avro(avro_config, key_deserialization, value_deserialization)
    validate_protobuf(protobuf_config, key_deserialization, value_deserialization)

    consumer_args = (
        topic,
        kafka_config,
        registry_config,
        protobuf_config,
        avro_config,
        key_deserialization,
        value_deserialization,
    )
    consumer_options: dict[str, Any] = {}
    if bytes_config:
        consumer_options["bytes_config"] = bytes_config
    if fallback_config:
        consumer_options["fallback_config"] = fallback_config
    if json_config:
        consumer_options["json_config"] = json_config
    if partitions:
        consumer_options["partitions"] = partitions
    consumer_options.update(application_timeout_options)
    try:
        kaskade_app = KaskadeConsumer(*consumer_args, **consumer_options)
    except PartitionSelectionError as ex:
        raise BadParameter(message=str(ex), param_hint="'--partition'") from ex
    except (KafkaException, ValueError) as ex:
        raise ClickException(str(ex)) from ex
    if theme is not None:
        kaskade_app.theme = theme
    kaskade_app.run()


def validate_deserializer(
    registry_config: dict[str, str],
    avro_config: dict[str, str],
    protobuf_config: dict[str, str],
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
) -> None:
    if len(avro_config) == 0 and (
        key_deserialization == Deserialization.AVRO or value_deserialization == Deserialization.AVRO
    ):
        raise MissingParameter(param_hint="'--avro'", param_type="option")

    if len(registry_config) == 0 and (
        key_deserialization == Deserialization.REGISTRY
        or value_deserialization == Deserialization.REGISTRY
    ):
        raise ClickException(
            "Schema Registry configuration is required. Use --registry or the "
            "[registry] section in --config-file."
        )

    if len(protobuf_config) == 0 and (
        key_deserialization == Deserialization.PROTOBUF
        or value_deserialization == Deserialization.PROTOBUF
    ):
        raise MissingParameter(param_hint="'--protobuf'", param_type="option")


def validate_properties(
    config: dict[str, str],
    valid_properties: list[str],
) -> None:
    if [property_name for property_name in config if property_name not in valid_properties]:
        raise BadParameter(message=f"Valid properties: {valid_properties}.")


def normalize_choices(
    config: dict[str, str],
    properties: list[str],
    choices: list[str],
    label: str,
) -> None:
    for property_name in properties:
        if property_name not in config:
            continue
        value = config[property_name].lower().replace("_", "-")
        if value not in choices:
            raise BadParameter(message=f"{label} should be one of {choices}.")
        config[property_name] = value


def validate_field_scope(
    config: dict[str, str],
    property_name: str,
    deserialization: Deserialization,
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
    option: str,
) -> None:
    if f"key.{property_name}" in config and key_deserialization != deserialization:
        raise BadParameter(f"{option} key.{property_name} requires '-k {deserialization}'.")
    if f"value.{property_name}" in config and value_deserialization != deserialization:
        raise BadParameter(f"{option} value.{property_name} requires '-v {deserialization}'.")


def validate_bytes(
    bytes_config: dict[str, str],
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
) -> None:
    if len(bytes_config) == 0:
        return
    validate_properties(bytes_config, BYTES_DESERIALIZER_CONFIGS)
    normalize_choices(
        bytes_config,
        BYTES_DESERIALIZER_CONFIGS,
        BYTES_ENCODINGS,
        "Bytes encoding",
    )
    if (
        key_deserialization != Deserialization.BYTES
        and value_deserialization != Deserialization.BYTES
    ):
        raise MissingParameter(param_hint="'-k bytes' and/or '-v bytes'", param_type="option")
    validate_field_scope(
        bytes_config,
        "encoding",
        Deserialization.BYTES,
        key_deserialization,
        value_deserialization,
        "--bytes",
    )


def validate_fallback(fallback_config: dict[str, str]) -> None:
    validate_properties(fallback_config, FALLBACK_CONFIGS)
    normalize_choices(
        fallback_config,
        FALLBACK_CONFIGS,
        BYTES_ENCODINGS,
        "Fallback encoding",
    )


def validate_json(
    json_config: dict[str, str],
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
) -> None:
    if len(json_config) == 0:
        return
    validate_properties(json_config, JSON_DESERIALIZER_CONFIGS)
    normalize_choices(
        json_config,
        JSON_DESERIALIZER_CONFIGS,
        DESERIALIZER_FRAMINGS,
        "JSON framing",
    )
    if (
        key_deserialization != Deserialization.JSON
        and value_deserialization != Deserialization.JSON
    ):
        raise MissingParameter(param_hint="'-k json' and/or '-v json'", param_type="option")
    validate_field_scope(
        json_config,
        "framing",
        Deserialization.JSON,
        key_deserialization,
        value_deserialization,
        "--json",
    )


def validate_avro(
    avro_config: dict[str, str],
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
) -> None:
    if len(avro_config) == 0:
        return

    validate_properties(avro_config, AVRO_DESERIALIZER_CONFIGS)
    normalize_choices(
        avro_config,
        FRAMING_CONFIGS,
        DESERIALIZER_FRAMINGS,
        "Avro framing",
    )

    if (
        key_deserialization != Deserialization.AVRO
        and value_deserialization != Deserialization.AVRO
    ):
        raise MissingParameter(param_hint="'-k avro' and/or '-v avro'", param_type="option")

    value = avro_config.get("value")
    key = avro_config.get("key")

    if value is None and value_deserialization == Deserialization.AVRO:
        raise MissingParameter(param_hint="'--avro value=my-schema.avsc'", param_type="option")

    if key is None and key_deserialization == Deserialization.AVRO:
        raise MissingParameter(param_hint="'--avro key=my-schema.avsc'", param_type="option")

    if value is not None:
        is_file(value)

    if key is not None:
        is_file(key)

    validate_field_scope(
        avro_config,
        "framing",
        Deserialization.AVRO,
        key_deserialization,
        value_deserialization,
        "--avro",
    )


def validate_schema_registry_usage(
    registry_config: dict[str, str],
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
) -> None:
    if len(registry_config) == 0:
        return

    if (
        key_deserialization != Deserialization.REGISTRY
        and value_deserialization != Deserialization.REGISTRY
    ):
        raise MissingParameter(param_hint="'-k registry' and/or '-v registry'", param_type="option")


def validate_registry_config(registry_config: dict[str, str]) -> None:
    if not registry_config:
        return
    provider_value = registry_config.get("provider", CONFLUENT_OPTION)
    provider = provider_value.lower()
    if provider not in REGISTRY_PROVIDERS:
        raise BadParameter(
            message=f"Registry provider should be one of {REGISTRY_PROVIDERS}.",
            param_hint="'--registry provider'",
        )
    if "provider" in registry_config:
        registry_config["provider"] = provider
    apicurio_properties = [key for key in registry_config if key.startswith(APICURIO_PREFIX)]
    if provider == CONFLUENT_OPTION and apicurio_properties:
        raise BadParameter(
            message=f"apicurio.registry.* properties require provider={APICURIO_OPTION}.",
            param_hint="'--registry'",
        )
    if provider == APICURIO_OPTION:
        try:
            ApicurioConfig.from_dict(registry_config)
        except (ApicurioRegistryError, OSError, ValueError) as ex:
            raise BadParameter(message=str(ex), param_hint="'--registry'") from ex


def validate_protobuf(
    protobuf_config: dict[str, str],
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
) -> None:
    if len(protobuf_config) == 0:
        return

    validate_properties(protobuf_config, PROTOBUF_DESERIALIZER_CONFIGS)
    normalize_choices(
        protobuf_config,
        FRAMING_CONFIGS,
        DESERIALIZER_FRAMINGS,
        "Protobuf framing",
    )

    descriptor_path_str = protobuf_config.get("descriptor")

    if descriptor_path_str is None:
        raise MissingParameter(
            param_hint="'--protobuf descriptor=my-descriptor'", param_type="option"
        )

    is_file(descriptor_path_str)

    if protobuf_config.get("value") is None and value_deserialization == Deserialization.PROTOBUF:
        raise MissingParameter(param_hint="'--protobuf value=MyMessage'", param_type="option")

    if protobuf_config.get("key") is None and key_deserialization == Deserialization.PROTOBUF:
        raise MissingParameter(param_hint="'--protobuf key=MyMessage'", param_type="option")

    if (
        key_deserialization != Deserialization.PROTOBUF
        and value_deserialization != Deserialization.PROTOBUF
    ):
        raise MissingParameter(param_hint="'-k protobuf' and/or '-v protobuf'", param_type="option")

    validate_field_scope(
        protobuf_config,
        "framing",
        Deserialization.PROTOBUF,
        key_deserialization,
        value_deserialization,
        "--protobuf",
    )


def is_file(file_path_str: str) -> None:
    if file_path_str is None:
        raise BadParameter("File path should be provided.")

    path = Path(file_path_str).expanduser()
    if not path.exists():
        raise BadParameter("File should exist.")

    if path.is_dir():
        raise BadParameter("Path is a directory.")


if __name__ == "__main__":
    cli()
