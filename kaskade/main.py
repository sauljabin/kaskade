from typing import Any

import cloup
from click import BadParameter, MissingParameter

from kaskade import APP_VERSION
from kaskade.admin import KaskadeAdmin
from kaskade.consumer import KaskadeConsumer
from kaskade.models import Format

epilog = "More information at https://github.com/sauljabin/kaskade."


def tuple_properties_to_dict(ctx: Any, param: Any, value: Any) -> Any:
    if [pair for pair in value if "=" not in pair]:
        raise BadParameter(message="Should be property=value.", ctx=ctx, param=param)

    return {k: v for (k, v) in [pair.split("=", 1) for pair in value]}


def string_to_format(ctx: Any, param: Any, value: Any) -> Any:
    if value not in Format.str_list():
        raise BadParameter(message=f"Should be one of {Format.str_list()}", ctx=ctx, param=param)

    return Format.from_str(value)


@cloup.group(epilog=epilog)
@cloup.version_option(APP_VERSION)
def cli() -> None:
    """kaskade is a terminal user interface for kafka."""
    pass


@cli.command(epilog=epilog)
@cloup.option_group(
    "Kafka options",
    cloup.option(
        "-b",
        "bootstrap_servers",
        help="Bootstrap server(s). Comma-separated list of host and port pairs. Example: localhost:9091,localhost:9092.",
        metavar="host:port",
        required=True,
    ),
    cloup.option(
        "-x",
        "kafka_config",
        help="Kafka property. Set a librdkafka configuration property. Multiple -x are allowed.",
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


@cli.command(epilog=epilog)
@cloup.option_group(
    "Kafka options",
    cloup.option(
        "-b",
        "bootstrap_servers",
        help="Bootstrap server(s). Comma-separated list of host and port pairs. Example: localhost:9091,localhost:9092.",
        metavar="host:port",
        required=True,
    ),
    cloup.option(
        "-x",
        "kafka_config",
        help="Kafka property. Set a librdkafka configuration property. Multiple -x are allowed.",
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
        help="Topic.",
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
        help="Schema Registry property. Set a SchemaRegistryClient property. Multiple -s are allowed. Needed if -k avro "
        "or -v avro were passed.",
        metavar="property=value",
        multiple=True,
        callback=tuple_properties_to_dict,
    ),
)
def consumer(
    bootstrap_servers: str,
    kafka_config: dict[str, str],
    schema_registry_config: dict[str, str],
    topic: str,
    key_format: Format,
    value_format: Format,
) -> None:
    """
    Consumer mode.

    \b
    Examples:
      kaskade consumer -b localhost:9092 -t my-topic
      kaskade consumer -b localhost:9092 -t my-topic -k string -v json
      kaskade consumer -b localhost:9092 -t my-topic -x auto.offset.reset=earliest
      kaskade consumer -b localhost:9092 -t my-topic -s url=http://localhost:8081 -v avro
    """
    kafka_config["bootstrap.servers"] = bootstrap_servers

    validate_schema_registry_url(schema_registry_config)
    validate_formats(schema_registry_config, key_format, value_format)

    kaskade_app = KaskadeConsumer(
        topic, kafka_config, schema_registry_config, key_format, value_format
    )
    kaskade_app.run()


def validate_formats(
    schema_registry_config: dict[str, str], key_format: Format, value_format: Format
) -> None:
    if len(schema_registry_config) == 0 and (
        key_format == Format.AVRO or value_format == Format.AVRO
    ):
        raise MissingParameter(param_hint="'-s'", param_type="option")

    if (
        len(schema_registry_config) > 0
        and key_format != Format.AVRO
        and value_format != Format.AVRO
    ):
        raise MissingParameter(param_hint="'-k avro' and/or '-v avro'", param_type="option")


def validate_schema_registry_url(schema_registry_config: dict[str, str]) -> None:
    if len(schema_registry_config) > 0 and schema_registry_config.get("url") is None:
        raise MissingParameter(param_hint="'-s url=<my url>'", param_type="option")


if __name__ == "__main__":
    cli()
