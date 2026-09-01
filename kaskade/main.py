import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import cloup
from click import BadParameter, ClickException, MissingParameter
from cloup.constraints import mutually_exclusive
from confluent_kafka import KafkaException

from kaskade import APP_VERSION
from kaskade.admin import KaskadeAdmin
from kaskade.authentication import configure_aws_msk_iam
from kaskade.cli_utils import tuple_properties_to_dict, validate_aws_config
from kaskade.configs import (
    AUTO_OFFSET_RESET,
    AVRO_DESERIALIZER_CONFIGS,
    AVRO_FRAMINGS,
    AWS_CONFIGS,
    BOOTSTRAP_SERVERS,
    EARLIEST,
    PROTOBUF_DESERIALIZER_CONFIGS,
    SCHEMA_REGISTRY_CONFIGS,
)
from kaskade.consumer import KaskadeConsumer
from kaskade.deserializers import Deserialization
from kaskade.keymaps import (
    MIN_ADMIN_REFRESH_INTERVAL_SECONDS,
    is_valid_admin_refresh_interval,
)
from kaskade.logs import configure_logging
from kaskade.models import PartitionOffset, PartitionSelection
from kaskade.services import PartitionSelectionError
from kaskade.themes import DEFAULT_THEME, available_theme_names
from kaskade.utils import load_properties

KAFKA_CONFIG_HELP = (
    "Kafka client property. Repeatable; overrides matching properties from --config-file."
)
KAFKA_CONFIG_FILE_HELP = (
    "Kafka client property file in property=value format. May provide bootstrap.servers."
)
BOOTSTRAP_SERVERS_HELP = (
    "Bootstrap servers. Comma-separated host:port pairs; overrides bootstrap.servers "
    "from Kafka client configuration."
)
BOOTSTRAP_SERVERS_REQUIRED = (
    "Bootstrap servers are required. Use -b/--bootstrap-servers or set "
    "bootstrap.servers with --config or --config-file."
)
EPILOG_HELP = "More information at https://github.com/sauljabin/kaskade."
EARLIEST_HELP = "Read all partitions from their earliest available offsets."
PARTITION_SELECTION_METAVAR = "partition[:offset|earliest]"
PARTITION_SELECTION_SYNTAX = "<partition>[:<absolute-offset|earliest>]"
PARTITION_SELECTION_HELP = (
    "Consume only this partition, optionally from an absolute offset or its earliest "
    f"available offset. Format: {PARTITION_SELECTION_METAVAR}. Repeatable."
)
PARTITION_SELECTION_PATTERN = re.compile(
    rf"(?P<partition>[0-9]+)(?::(?P<offset>[0-9]+|{re.escape(EARLIEST)}))?"
)
AWS_CONFIG_HELP = f"Amazon MSK IAM property. Repeatable. Properties: {', '.join(AWS_CONFIGS)}."
THEME_HELP = "Textual theme name. See USAGE.md or use the in-application Commands window."
AVRO_CONFIG_HELP = (
    "Avro deserializer property. Repeatable; required when the key or value format is "
    "avro. Properties: key, value, framing."
)
PROTOBUF_CONFIG_HELP = (
    "Protobuf deserializer property. Repeatable; required when the key or value format "
    "is protobuf. Properties: descriptor, key, value."
)
REGISTRY_CONFIG_HELP = (
    "Schema Registry client property. Repeatable; required when the key or value format "
    "is registry."
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
            "-c",
            "--config",
            "kafka_config",
            help=KAFKA_CONFIG_HELP,
            metavar="property=value",
            multiple=True,
            callback=tuple_properties_to_dict,
        ),
        cloup.option(
            "--config-file",
            "kafka_config_file",
            help=KAFKA_CONFIG_FILE_HELP,
            type=cloup.Path(exists=True),
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


def theme_option() -> Callable[[CliDecoratorTarget], CliDecoratorTarget]:
    return cloup.option(
        "--theme",
        type=cloup.Choice(available_theme_names(), case_sensitive=False),
        default=DEFAULT_THEME,
        show_default=True,
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
            help="Admin auto-refresh interval. Use 0 to disable; overrides config.yaml.",
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


def resolve_kafka_config(
    bootstrap_servers: str | None,
    kafka_config_file: str | None,
    kafka_config: dict[str, Any],
) -> dict[str, Any]:
    resolved_config = dict(kafka_config)
    if kafka_config_file is not None:
        resolved_config = load_properties(kafka_config_file) | resolved_config

    if bootstrap_servers is not None:
        resolved_config[BOOTSTRAP_SERVERS] = bootstrap_servers

    resolved_bootstrap_servers = resolved_config.get(BOOTSTRAP_SERVERS)
    if not isinstance(resolved_bootstrap_servers, str) or not resolved_bootstrap_servers.strip():
        raise ClickException(BOOTSTRAP_SERVERS_REQUIRED)

    return resolved_config


@cloup.group(epilog=EPILOG_HELP)
@cloup.version_option(APP_VERSION)
def cli() -> None:
    """kaskade is a terminal user interface for kafka."""
    configure_logging()


@cli.command(epilog=EPILOG_HELP)
@kafka_connection_options()
@aws_options()
@admin_application_options()
def admin(
    bootstrap_servers: str | None,
    kafka_config_file: str | None,
    kafka_config: dict[str, Any],
    aws_config: dict[str, str],
    theme: str,
    refresh_interval: int | None,
) -> None:
    """
    Administrator mode.

    \b
    Examples:
      kaskade admin -b localhost:9092
      kaskade admin -b localhost:9092 --refresh-interval 10
      kaskade admin -b localhost:9092 --config security.protocol=SSL
      kaskade admin --config bootstrap.servers=localhost:9092
      kaskade admin --config-file kafka.properties
      kaskade admin -b localhost:9092 --aws region=us-east-1
    """

    kafka_config = resolve_kafka_config(bootstrap_servers, kafka_config_file, kafka_config)
    validate_aws_config(aws_config)
    kafka_config = configure_aws_msk_iam(kafka_config, aws_config)

    kaskade_app = KaskadeAdmin(kafka_config, refresh_interval=refresh_interval)
    kaskade_app.theme = theme
    kaskade_app.run()


@cli.command(epilog=EPILOG_HELP, show_constraints=True)
@kafka_connection_options()
@aws_options()
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
        help="Key deserializer.",
        default=str(Deserialization.BYTES),
        show_default=True,
        callback=string_to_deserializer_type,
    ),
    cloup.option(
        "-v",
        "--value",
        "value_deserialization",
        type=cloup.Choice(Deserialization.str_list(), False),
        help="Value deserializer.",
        default=str(Deserialization.BYTES),
        show_default=True,
        callback=string_to_deserializer_type,
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
    topic: str,
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
    earliest: bool,
    partitions: tuple[PartitionSelection, ...],
    kafka_config_file: str | None,
    aws_config: dict[str, str],
    theme: str,
) -> None:
    """
    Consumer mode.

    \b
    Examples:
      kaskade consumer -b localhost:9092 -t my-topic
      kaskade consumer -b localhost:9092 -t my-topic --earliest
      kaskade consumer -b localhost:9092 -t my-topic --partition 1:10 --partition 2:earliest
      kaskade consumer -b localhost:9092 -t my-topic --config security.protocol=SSL
      kaskade consumer -t my-topic --config bootstrap.servers=localhost:9092
      kaskade consumer -t my-topic --config-file kafka.properties
      kaskade consumer -b localhost:9092 -t my-topic --aws region=us-east-1
      kaskade consumer -b localhost:9092 -t my-topic -v json
      kaskade consumer -b localhost:9092 -t my-topic -v registry --registry url=http://localhost:8081
      kaskade consumer -b localhost:9092 -t my-topic -v avro --avro value=my-schema.avsc
      kaskade consumer -b localhost:9092 -t my-topic -v protobuf --protobuf descriptor=my-descriptor.desc --protobuf value=MyMessage
    """

    kafka_config = resolve_kafka_config(bootstrap_servers, kafka_config_file, kafka_config)
    validate_aws_config(aws_config)
    kafka_config = configure_aws_msk_iam(kafka_config, aws_config)

    if earliest:
        kafka_config[AUTO_OFFSET_RESET] = EARLIEST

    validate_deserializer(
        registry_config, avro_config, protobuf_config, key_deserialization, value_deserialization
    )
    validate_schema_registry(registry_config, key_deserialization, value_deserialization)
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
    try:
        if partitions:
            kaskade_app = KaskadeConsumer(*consumer_args, partitions=partitions)
        else:
            kaskade_app = KaskadeConsumer(*consumer_args)
    except PartitionSelectionError as ex:
        raise BadParameter(message=str(ex), param_hint="'--partition'") from ex
    except KafkaException as ex:
        raise ClickException(str(ex)) from ex
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
        raise MissingParameter(param_hint="'--registry'", param_type="option")

    if len(protobuf_config) == 0 and (
        key_deserialization == Deserialization.PROTOBUF
        or value_deserialization == Deserialization.PROTOBUF
    ):
        raise MissingParameter(param_hint="'--protobuf'", param_type="option")


def validate_avro(
    avro_config: dict[str, str],
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
) -> None:
    if len(avro_config) == 0:
        return

    if [config for config in avro_config if config not in AVRO_DESERIALIZER_CONFIGS]:
        raise BadParameter(message=f"Valid properties: {AVRO_DESERIALIZER_CONFIGS}.")

    framing = avro_config.get("framing", "raw")
    if framing not in AVRO_FRAMINGS:
        raise BadParameter(message=f"Avro framing should be one of {AVRO_FRAMINGS}.")

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


def validate_schema_registry(
    registry_config: dict[str, str],
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
) -> None:
    if len(registry_config) == 0:
        return

    if [config for config in registry_config if config not in SCHEMA_REGISTRY_CONFIGS]:
        raise BadParameter(message=f"Valid properties: {SCHEMA_REGISTRY_CONFIGS}.")

    url = registry_config.get("url")

    if (
        key_deserialization != Deserialization.REGISTRY
        and value_deserialization != Deserialization.REGISTRY
    ):
        raise MissingParameter(param_hint="'-k registry' and/or '-v registry'", param_type="option")

    if url is None:
        raise MissingParameter(param_hint="'--registry url=my-url'", param_type="option")

    if not url.startswith("http://") and not url.startswith("https://"):
        raise BadParameter("Invalid url.")


def validate_protobuf(
    protobuf_config: dict[str, str],
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
) -> None:
    if len(protobuf_config) == 0:
        return

    if [config for config in protobuf_config if config not in PROTOBUF_DESERIALIZER_CONFIGS]:
        raise BadParameter(message=f"Valid properties: {PROTOBUF_DESERIALIZER_CONFIGS}.")

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
