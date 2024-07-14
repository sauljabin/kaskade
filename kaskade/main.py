from pathlib import Path
from typing import Any

import cloup
from click import BadParameter, MissingParameter

from kaskade import APP_VERSION
from kaskade.admin import KaskadeAdmin
from kaskade.consumer import KaskadeConsumer
from kaskade.deserializers import Format
from kaskade.configs import SCHEMA_REGISTRY_CONFIGS, PROTOBUF_DESERIALIZER_CONFIGS

KAFKA_CONFIG_HELP = (
    "Kafka property. Set a librdkafka configuration property. Multiple '-x' are allowed."
)
BOOTSTRAP_SERVERS_HELP = "Bootstrap server(s). Comma-separated list of host and port pairs. Example: '-b localhost:9091,localhost:9092'."
EPILOG_HELP = "More information at https://github.com/sauljabin/kaskade."


def tuple_properties_to_dict(ctx: Any, param: Any, value: Any) -> Any:
    if [pair for pair in value if "=" not in pair]:
        raise BadParameter(message="Should be property=value.", ctx=ctx, param=param)

    return {k: v for (k, v) in [pair.split("=", 1) for pair in value]}


def string_to_format(ctx: Any, param: Any, value: Any) -> Any:
    if value not in Format.str_list():
        raise BadParameter(message=f"Should be one of {Format.str_list()}", ctx=ctx, param=param)

    return Format.from_str(value)


@cloup.group(epilog=EPILOG_HELP)
@cloup.version_option(APP_VERSION)
def cli() -> None:
    """kaskade is a terminal user interface for kafka."""
    pass


@cli.command(epilog=EPILOG_HELP)
@cloup.option_group(
    "Kafka options",
    cloup.option(
        "-b",
        "bootstrap_servers",
        help=BOOTSTRAP_SERVERS_HELP,
        metavar="host:port",
        required=True,
    ),
    cloup.option(
        "-x",
        "kafka_config",
        help=KAFKA_CONFIG_HELP,
        metavar="property=value",
        multiple=True,
        callback=tuple_properties_to_dict,
    ),
)
def admin(
    bootstrap_servers: str,
    kafka_config: dict[str, str],
) -> None:
    """
    Administrator mode.

    \b
    Examples:
      kaskade admin -b localhost:9092
      kaskade admin -b localhost:9092 -x security.protocol=SSL
    """
    kafka_config["bootstrap.servers"] = bootstrap_servers
    kaskade_app = KaskadeAdmin(kafka_config)
    kaskade_app.run()


@cli.command(epilog=EPILOG_HELP)
@cloup.option_group(
    "Kafka options",
    cloup.option(
        "-b",
        "bootstrap_servers",
        help=BOOTSTRAP_SERVERS_HELP,
        metavar="host:port",
        required=True,
    ),
    cloup.option(
        "-x",
        "kafka_config",
        help=KAFKA_CONFIG_HELP,
        metavar="property=value",
        multiple=True,
        callback=tuple_properties_to_dict,
    ),
)
@cloup.option_group(
    "Topic options",
    cloup.option(
        "-t",
        "topic",
        help="Topic name.",
        metavar="name",
        required=True,
    ),
    cloup.option(
        "-k",
        "key_format",
        type=cloup.Choice(Format.str_list(), False),
        help="Key format.",
        default=str(Format.BYTES),
        show_default=True,
        callback=string_to_format,
    ),
    cloup.option(
        "-v",
        "value_format",
        type=cloup.Choice(Format.str_list(), False),
        help="Value format.",
        default=str(Format.BYTES),
        show_default=True,
        callback=string_to_format,
    ),
)
@cloup.option_group(
    "Schema Registry options",
    cloup.option(
        "-s",
        "schema_registry_config",
        help="Schema Registry property. Set a SchemaRegistryClient property. Multiple '-s' are allowed. Needed if '-k avro' "
        "or '-v avro' were passed.",
        metavar="property=value",
        multiple=True,
        callback=tuple_properties_to_dict,
    ),
)
@cloup.option_group(
    "Protobuf options",
    cloup.option(
        "-p",
        "protobuf_config",
        help="Protobuf property. Configure the protobuf deserializer. Multiple '-p' are allowed. Needed if '-k protobuf' "
        "or '-v protobuf' were passed. Valid properties: [descriptor: file path, key: protobuf message, value: protobuf message].",
        metavar="property=value",
        multiple=True,
        callback=tuple_properties_to_dict,
    ),
)
def consumer(
    bootstrap_servers: str,
    kafka_config: dict[str, str],
    schema_registry_config: dict[str, str],
    protobuf_config: dict[str, str],
    topic: str,
    key_format: Format,
    value_format: Format,
) -> None:
    """
    Consumer mode.

    \b
    Examples:
      kaskade consumer -b localhost:9092 -t my-topic
      kaskade consumer -b localhost:9092 -t my-topic -x auto.offset.reset=earliest
      kaskade consumer -b localhost:9092 -t my-topic -v json
      kaskade consumer -b localhost:9092 -t my-topic -v avro -s url=http://localhost:8081
      kaskade consumer -b localhost:9092 -t my-topic -v protobuf -p descriptor=my-descriptor.desc -p value=MyMessage
    """
    kafka_config["bootstrap.servers"] = bootstrap_servers

    validate_schema_registry(schema_registry_config, key_format, value_format)
    validate_protobuf(protobuf_config, key_format, value_format)

    kaskade_app = KaskadeConsumer(
        topic, kafka_config, schema_registry_config, protobuf_config, key_format, value_format
    )
    kaskade_app.run()


def validate_schema_registry(
    schema_registry_config: dict[str, str], key_format: Format, value_format: Format
) -> None:
    if [
        config for config in schema_registry_config.keys() if config not in SCHEMA_REGISTRY_CONFIGS
    ]:
        raise BadParameter(message=f"Valid properties: {SCHEMA_REGISTRY_CONFIGS}.")

    config_size = len(schema_registry_config)
    url = schema_registry_config.get("url")

    if config_size == 0:
        if key_format == Format.AVRO or value_format == Format.AVRO:
            raise MissingParameter(param_hint="'-s'", param_type="option")

    if config_size > 0:
        if key_format != Format.AVRO and value_format != Format.AVRO:
            raise MissingParameter(param_hint="'-k avro' and/or '-v avro'", param_type="option")

        if url is None:
            raise MissingParameter(param_hint="'-s url=my-url'", param_type="option")

        if not url.startswith("http://") and not url.startswith("https://"):
            raise BadParameter("Invalid url.")


def validate_protobuf(
    protobuf_config: dict[str, str], key_format: Format, value_format: Format
) -> None:
    if [config for config in protobuf_config.keys() if config not in PROTOBUF_DESERIALIZER_CONFIGS]:
        raise BadParameter(message=f"Valid properties: {PROTOBUF_DESERIALIZER_CONFIGS}.")

    config_size = len(protobuf_config)
    descriptor_path_str = protobuf_config.get("descriptor")

    if config_size == 0:
        if key_format == Format.PROTOBUF or value_format == Format.PROTOBUF:
            raise MissingParameter(param_hint="'-p'", param_type="option")

    if config_size > 0:
        if descriptor_path_str is None:
            raise MissingParameter(param_hint="'-p descriptor=my-descriptor'", param_type="option")

        descriptor_path = Path(descriptor_path_str).expanduser()

        if not descriptor_path.exists():
            raise BadParameter("File should exist.")

        if descriptor_path.is_dir():
            raise BadParameter("Path is a directory.")

        if protobuf_config.get("value") is None and value_format == Format.PROTOBUF:
            raise MissingParameter(param_hint="'-p value=MyMessage'", param_type="option")

        if protobuf_config.get("key") is None and key_format == Format.PROTOBUF:
            raise MissingParameter(param_hint="'-p key=MyMessage'", param_type="option")

        if key_format != Format.PROTOBUF and value_format != Format.PROTOBUF:
            raise MissingParameter(
                param_hint="'-k protobuf' and/or '-v protobuf'", param_type="option"
            )


if __name__ == "__main__":
    cli()
