import re
from collections.abc import Callable
from typing import Any, TypeVar

import cloup
from click import BadParameter, Choice, ClickException
from cloup.constraints import mutually_exclusive
from confluent_kafka import KafkaException

from kaskade import APP_VERSION
from kaskade.admin import KaskadeAdmin
from kaskade.cli.connection import load_config_file, resolve_connection
from kaskade.cli.properties import tuple_properties_to_dict
from kaskade.cli.validation import normalize_deserializer_options
from kaskade.configs import (
    APICURIO_OPTION,
    AUTO_OFFSET_RESET,
    AVRO_DESERIALIZER_CONFIGS,
    AWS_CONFIGS,
    BYTES_DESERIALIZER_CONFIGS,
    BYTES_ENCODINGS,
    CONFLUENT_OPTION,
    DESERIALIZER_FRAMINGS,
    EARLIEST,
    FALLBACK_CONFIGS,
    JSON_DESERIALIZER_CONFIGS,
    PROTOBUF_DESERIALIZER_CONFIGS,
    REGISTRY_PROVIDERS,
)
from kaskade.consumer import KaskadeConsumer
from kaskade.consumer_service import ConsumerSettings, PartitionSelectionError
from kaskade.deserializers import Deserialization
from kaskade.logs import configure_logging
from kaskade.models import PartitionOffset, PartitionSelection
from kaskade.settings import (
    MIN_ADMIN_REFRESH_INTERVAL_SECONDS,
    is_valid_admin_refresh_interval,
)
from kaskade.themes import configured_theme_names
from kaskade.timeouts import TIMEOUT_PROPERTIES, TimeoutConfig

KAFKA_CONFIG_HELP = (
    "Kafka client property. Repeatable; overrides matching properties from --config-file."
)
CONFIG_FILE_HELP = (
    "INI file with [kafka], [registry], [aws], and/or [timeouts] configuration sections."
)
BOOTSTRAP_SERVERS_HELP = (
    "Bootstrap servers. Comma-separated host:port pairs; overrides bootstrap.servers "
    "from Kafka client configuration."
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
    "Textual, Kaskade, or settings.yaml custom theme name; overrides settings.yaml. When "
    "omitted, settings.yaml or Eva01 Berserk is used."
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


class ThemeChoice(Choice[str]):
    """Theme names, read from settings.yaml only when --theme is parsed or completed."""

    def __init__(self) -> None:
        self.case_sensitive = False

    # Click assigns choices in __init__; loading them lazily keeps import free of file reads.
    @property
    def choices(self) -> tuple[str, ...]:  # type: ignore[override]
        return configured_theme_names()


def theme_option() -> Callable[[CliDecoratorTarget], CliDecoratorTarget]:
    return cloup.option(
        "--theme",
        type=ThemeChoice(),
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
    """Kafka in your terminal."""
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
    connection = resolve_connection(file_config, bootstrap_servers, kafka_config, aws_config)
    application_timeout_options = configured_timeout_options(
        file_config.get("timeouts", {}), timeout_config
    )

    admin_options: dict[str, Any] = {
        "refresh_interval": refresh_interval,
        **application_timeout_options,
    }
    kaskade_app = KaskadeAdmin(connection.kafka_config, **admin_options)
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
      kaskade consumer -b localhost:9092 -t my-topic --bytes encoding=hex --fallback encoding=hex
      kaskade consumer -b localhost:9092 -t my-topic -v registry --registry url=http://localhost:8081
    """

    file_config = load_config_file(config_file)
    connection = resolve_connection(
        file_config, bootstrap_servers, kafka_config, aws_config, registry_config
    )
    application_timeout_options = configured_timeout_options(
        file_config.get("timeouts", {}), timeout_config
    )
    kafka_config = connection.kafka_config
    if earliest:
        kafka_config = kafka_config | {AUTO_OFFSET_RESET: EARLIEST}

    options = normalize_deserializer_options(
        key_deserialization,
        value_deserialization,
        registry_config=connection.registry_config,
        protobuf_config=protobuf_config,
        avro_config=avro_config,
        json_config=json_config,
        bytes_config=bytes_config,
        fallback_config=fallback_config,
    )
    settings = ConsumerSettings(
        topic=topic,
        kafka_config=kafka_config,
        key_deserialization=key_deserialization,
        value_deserialization=value_deserialization,
        registry_config=options.registry_config,
        apicurio_config=options.apicurio_config,
        protobuf_config=options.protobuf_config,
        avro_config=options.avro_config,
        json_config=options.json_config,
        bytes_config=options.bytes_config,
        fallback_config=options.fallback_config,
        partitions=partitions,
        **application_timeout_options,
    )
    try:
        kaskade_app = KaskadeConsumer(settings)
    except PartitionSelectionError as ex:
        raise BadParameter(message=str(ex), param_hint="'--partition'") from ex
    except (KafkaException, ValueError) as ex:
        raise ClickException(str(ex)) from ex
    if theme is not None:
        kaskade_app.theme = theme
    kaskade_app.run()


if __name__ == "__main__":
    cli()
