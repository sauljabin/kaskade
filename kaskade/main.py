from pathlib import Path
from typing import Any

import cloup
from click import BadParameter, MissingParameter

from kaskade import APP_VERSION
from kaskade.admin import KaskadeAdmin
from kaskade.consumer import KaskadeConsumer
from kaskade.deserializers import Deserialization
from kaskade.configs import (
    BOOTSTRAP_SERVERS,
    SCHEMA_REGISTRY_CONFIGS,
    PROTOBUF_DESERIALIZER_CONFIGS,
    AUTO_OFFSET_RESET,
    EARLIEST,
    AVRO_DESERIALIZER_CONFIGS,
)
from kaskade.utils import load_properties

KAFKA_CONFIG_HELP = (
    "Kafka property. Set a librdkafka configuration property. Multiple '-c' are allowed."
)
KAFKA_CONFIG_FILE_HELP = (
    "Property file (property=value format) containing configs to be passed to Kafka Client."
)
BOOTSTRAP_SERVERS_HELP = "Bootstrap server(s). Comma-separated list of host and port pairs. Example: '-b localhost:9091,localhost:9092'."
EPILOG_HELP = "More information at https://github.com/sauljabin/kaskade."


def tuple_properties_to_dict(ctx: Any, param: Any, value: Any) -> Any:
    if [pair for pair in value if "=" not in pair]:
        raise BadParameter(message="Should be property=value.", ctx=ctx, param=param)

    return {k: v for (k, v) in [pair.split("=", 1) for pair in value]}


def string_to_deserializer_type(ctx: Any, param: Any, value: Any) -> Any:
    if value not in Deserialization.str_list():
        raise BadParameter(
            message=f"Should be one of {Deserialization.str_list()}", ctx=ctx, param=param
        )

    return Deserialization.from_str(value)


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
        "--bootstrap-servers",
        "bootstrap_servers",
        help=BOOTSTRAP_SERVERS_HELP,
        metavar="host:port",
        required=True,
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
@cloup.option_group(
    "Cloud configuration options",
    cloup.option(
        "--cloud-config",
        "cloud_config",
        help="Cloud configuration properties. Typically used to set 'aws.region', which is required when using AWS MSK IAM authentication. Multiple '--cloud-config' are allowed",
        metavar="property=value",
        multiple=True,
        callback=tuple_properties_to_dict,
    ),
)
def admin(
    bootstrap_servers: str,
    kafka_config_file: str | None,
    kafka_config: dict[str, str],
    cloud_config: dict[str, str],
) -> None:
    """
    Administrator mode.

    \b
    Examples:
      kaskade admin -b localhost:9092
      kaskade admin -b localhost:9092 --config security.protocol=SSL
      kaskade admin -b localhost:9092 --config-file kafka.properties
      kaskade admin -b localhost:9092 -c security.protocol=SASL_SSL -c sasl.mechanism=OAUTHBEARER --cloud-config aws.region=eu-west-1
    """

    if kafka_config_file is not None:
        kafka_config = load_properties(kafka_config_file) | kafka_config

    kafka_config[BOOTSTRAP_SERVERS] = bootstrap_servers

    kaskade_app = KaskadeAdmin(kafka_config, cloud_config)
    kaskade_app.run()


@cli.command(epilog=EPILOG_HELP)
@cloup.option_group(
    "Kafka options",
    cloup.option(
        "-b",
        "--bootstrap-servers",
        "bootstrap_servers",
        help=BOOTSTRAP_SERVERS_HELP,
        metavar="host:port",
        required=True,
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
        "--from-beginning",
        "from_beginning",
        help="Read from beginning. Equivalent to: '-c auto.offset.reset=earliest'.",
        is_flag=True,
    ),
    cloup.option(
        "--config-file",
        "kafka_config_file",
        help=KAFKA_CONFIG_FILE_HELP,
        type=cloup.Path(exists=True),
        metavar="filename",
    ),
)
@cloup.option_group(
    "Topic options",
    cloup.option(
        "-t",
        "--topic",
        "topic",
        help="Topic name.",
        metavar="name",
        required=True,
    ),
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
        help="Avro property. Configure the avro deserializer. Multiple '--avro' are allowed. Needed if '-k avro' "
        "or '-v avro' were passed. Valid properties: [key: avsc file path, value: avsc file path].",
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
        help="Protobuf property. Configure the protobuf deserializer. Multiple '--protobuf' are allowed. Needed if '-k protobuf' "
        "or '-v protobuf' were passed. Valid properties: [descriptor: file path, key: protobuf message, value: protobuf message].",
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
        help="Schema Registry property. Set a SchemaRegistryClient property. Multiple '--registry' are allowed. Needed if '-k registry' "
        "or '-v registry' were passed.",
        metavar="property=value",
        multiple=True,
        callback=tuple_properties_to_dict,
    ),
)
@cloup.option_group(
    "Cloud configuration options",
    cloup.option(
        "--cloud-config",
        "cloud_config",
        help="Cloud configuration properties. Typically used to set 'aws.region', which is required when using AWS MSK IAM authentication. Multiple '--cloud-config' are allowed",
        metavar="property=value",
        multiple=True,
        callback=tuple_properties_to_dict,
    ),
)
def consumer(
    bootstrap_servers: str,
    kafka_config: dict[str, str],
    registry_config: dict[str, str],
    protobuf_config: dict[str, str],
    avro_config: dict[str, str],
    cloud_config: dict[str, str],
    topic: str,
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
    from_beginning: bool,
    kafka_config_file: str | None,
) -> None:
    """
    Consumer mode.

    \b
    Examples:
      kaskade consumer -b localhost:9092 -t my-topic
      kaskade consumer -b localhost:9092 -t my-topic --from-beginning
      kaskade consumer -b localhost:9092 -t my-topic --config security.protocol=SSL
      kaskade consumer -b localhost:9092 -t my-topic --config-file kafka.properties
      kaskade consumer -b localhost:9092 -t my-topic -c security.protocol=SASL_SSL -c sasl.mechanism=OAUTHBEARER --cloud-config aws.region=eu-west-1
      kaskade consumer -b localhost:9092 -t my-topic -v json
      kaskade consumer -b localhost:9092 -t my-topic -v registry --registry url=http://localhost:8081
      kaskade consumer -b localhost:9092 -t my-topic -v avro --avro value=my-schema.avsc
      kaskade consumer -b localhost:9092 -t my-topic -v protobuf --protobuf descriptor=my-descriptor.desc --protobuf value=MyMessage
    """

    if kafka_config_file is not None:
        kafka_config = load_properties(kafka_config_file) | kafka_config

    kafka_config[BOOTSTRAP_SERVERS] = bootstrap_servers

    if from_beginning:
        kafka_config[AUTO_OFFSET_RESET] = EARLIEST

    validate_deserializer(
        registry_config, avro_config, protobuf_config, key_deserialization, value_deserialization
    )
    validate_schema_registry(registry_config, key_deserialization, value_deserialization)
    validate_avro(avro_config, key_deserialization, value_deserialization)
    validate_protobuf(protobuf_config, key_deserialization, value_deserialization)

    kaskade_app = KaskadeConsumer(
        topic,
        kafka_config,
        registry_config,
        protobuf_config,
        avro_config,
        cloud_config,
        key_deserialization,
        value_deserialization,
    )
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

    if [config for config in avro_config.keys() if config not in AVRO_DESERIALIZER_CONFIGS]:
        raise BadParameter(message=f"Valid properties: {AVRO_DESERIALIZER_CONFIGS}.")

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

    if [config for config in registry_config.keys() if config not in SCHEMA_REGISTRY_CONFIGS]:
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

    if [config for config in protobuf_config.keys() if config not in PROTOBUF_DESERIALIZER_CONFIGS]:
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
