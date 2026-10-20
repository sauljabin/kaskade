from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from click import BadParameter, ClickException, MissingParameter
from confluent_kafka.serialization import MessageField

from kaskade.apicurio import APICURIO_PREFIX, ApicurioConfig, ApicurioRegistryError
from kaskade.configs import (
    APICURIO_OPTION,
    AVRO_DESERIALIZER_CONFIGS,
    AVRO_SERIALIZER_CONFIGS,
    BYTES_CONFIGS,
    BYTES_ENCODINGS,
    CONFLUENT_OPTION,
    DESERIALIZER_FRAMINGS,
    FALLBACK_CONFIGS,
    FRAMING_CONFIGS,
    JSON_DESERIALIZER_CONFIGS,
    JSON_SERIALIZER_CONFIGS,
    PROTOBUF_DESERIALIZER_CONFIGS,
    PROTOBUF_SCHEMA_CONFIGS,
    PROTOBUF_SERIALIZER_CONFIGS,
    REGISTRY_PROVIDERS,
)
from kaskade.deserializers import Deserialization
from kaskade.schemas import SchemaError
from kaskade.schemas.avro import load_avro_schema
from kaskade.schemas.json_schema import load_json_schema
from kaskade.serializers import SchemaSelection, Serialization, split_registry_config
from kaskade.serializers.local import local_message_class

Properties = Mapping[str, str]
Format = Deserialization | Serialization
"""A consumer or producer format; both enums name avro, protobuf, registry, and bytes."""


@dataclass(frozen=True)
class SerializerOptions:
    """Validated, normalized copies of the producer's serializer properties."""

    registry_config: dict[str, str]
    apicurio_config: ApicurioConfig | None
    protobuf_config: dict[str, str]
    avro_config: dict[str, str]
    json_config: dict[str, str]
    bytes_config: dict[str, str]


@dataclass(frozen=True)
class DeserializerOptions:
    """Validated, normalized copies of the consumer's deserializer properties."""

    registry_config: dict[str, str]
    apicurio_config: ApicurioConfig | None
    protobuf_config: dict[str, str]
    avro_config: dict[str, str]
    json_config: dict[str, str]
    bytes_config: dict[str, str]
    fallback_config: dict[str, str]


def normalize_deserializer_options(
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
    *,
    registry_config: Properties,
    protobuf_config: Properties,
    avro_config: Properties,
    json_config: Properties,
    bytes_config: Properties,
    fallback_config: Properties,
) -> DeserializerOptions:
    """Validate the deserializer properties and return normalized copies."""
    formats = (key_deserialization, value_deserialization)
    require_configured(registry_config, avro_config, protobuf_config, *formats)
    registry, apicurio = normalize_registry(registry_config, *formats)
    normalized_bytes = normalize_bytes(bytes_config, *formats)
    normalized_fallback = normalize_fallback(fallback_config)
    normalized_json = normalize_json(json_config, *formats, JSON_DESERIALIZER_CONFIGS)
    normalized_avro = normalize_avro(avro_config, *formats)
    normalized_protobuf = normalize_protobuf(protobuf_config, *formats)
    return DeserializerOptions(
        registry_config=registry,
        apicurio_config=apicurio,
        protobuf_config=normalized_protobuf,
        avro_config=normalized_avro,
        json_config=normalized_json,
        bytes_config=normalized_bytes,
        fallback_config=normalized_fallback,
    )


def normalize_serializer_options(
    key_serialization: Serialization,
    value_serialization: Serialization,
    *,
    registry_config: Properties,
    protobuf_config: Properties,
    avro_config: Properties,
    json_config: Properties,
    bytes_config: Properties,
) -> SerializerOptions:
    """Validate the serializer properties, including local schema files, and copy them."""
    formats = (key_serialization, value_serialization)
    require_configured(registry_config, avro_config, protobuf_config, *formats)
    registry, apicurio, registering = normalize_producer_registry(registry_config, *formats)
    # A registering Registry field takes its schema file as if it used that format.
    file_formats = schema_file_formats(
        formats, registering, avro=avro_config, json=json_config, protobuf=protobuf_config
    )
    normalized_json = normalize_json(json_config, *file_formats, JSON_SERIALIZER_CONFIGS)
    normalized_avro = normalize_producer_avro(avro_config, *file_formats)
    normalized_protobuf = normalize_producer_protobuf(protobuf_config, *file_formats)
    if apicurio is not None:
        require_protobuf_source(normalized_protobuf, registering)
    return SerializerOptions(
        registry_config=registry,
        apicurio_config=apicurio,
        protobuf_config=normalized_protobuf,
        avro_config=normalized_avro,
        json_config=normalized_json,
        bytes_config=normalize_bytes(bytes_config, *formats),
    )


def schema_file_formats(
    formats: tuple[Serialization, Serialization],
    registering: set[str],
    **configs: Properties,
) -> tuple[Serialization, Serialization]:
    """Each field's format for schema-file validation; registering fields use their file's."""
    result = []
    for field_name, serialization in zip(("key", "value"), formats, strict=True):
        found = [
            Serialization.from_str(name) for name, config in configs.items() if field_name in config
        ]
        if field_name not in registering:
            if serialization == Serialization.REGISTRY and found:
                raise BadParameter(
                    f"--{found[0]} {field_name} with a Registry {field_name} is the schema to "
                    "register; enable auto.register.schemas or apicurio.registry.auto-register.",
                    param_hint="'--registry'",
                )
            result.append(serialization)
            continue
        if len(found) != 1:
            raise BadParameter(
                f"Registering the {field_name} schema needs exactly one schema file: "
                f"--avro {field_name}=…, --json {field_name}=…, or --protobuf {field_name}=… "
                "with descriptor= or source=.",
                param_hint="'--registry'",
            )
        result.append(found[0])
    key_format, value_format = result
    return key_format, value_format


def require_protobuf_source(protobuf_config: Properties, registering: set[str]) -> None:
    """Apicurio stores .proto text, which only a source= file has."""
    if "descriptor" in protobuf_config and registering.intersection(protobuf_config):
        raise BadParameter(
            "Registering Protobuf in Apicurio needs --protobuf source=my.proto.",
            param_hint="'--protobuf descriptor'",
        )


def uses(
    deserialization: Format,
    key_deserialization: Format,
    value_deserialization: Format,
) -> bool:
    return deserialization in (key_deserialization, value_deserialization)


def require_usage(
    deserialization: Format,
    key_deserialization: Format,
    value_deserialization: Format,
) -> None:
    if not uses(deserialization, key_deserialization, value_deserialization):
        raise MissingParameter(
            param_hint=f"'-k {deserialization}' and/or '-v {deserialization}'",
            param_type="option",
        )


def require_configured(
    registry_config: Properties,
    avro_config: Properties,
    protobuf_config: Properties,
    key_deserialization: Format,
    value_deserialization: Format,
) -> None:
    formats = (key_deserialization, value_deserialization)
    kind = type(key_deserialization)
    if not avro_config and uses(kind.AVRO, *formats):
        raise MissingParameter(param_hint="'--avro'", param_type="option")

    if not registry_config and uses(kind.REGISTRY, *formats):
        raise ClickException(
            "Schema Registry configuration is required. Use --registry or the "
            "[registry] section in --config-file."
        )

    if not protobuf_config and uses(kind.PROTOBUF, *formats):
        raise MissingParameter(param_hint="'--protobuf'", param_type="option")


def require_field_properties(
    config: Properties,
    deserialization: Format,
    key_deserialization: Format,
    value_deserialization: Format,
    option: str,
    example: str,
) -> None:
    """Require a value and key property for each field that uses the format."""
    for field_name, field_deserialization in (
        ("value", value_deserialization),
        ("key", key_deserialization),
    ):
        if field_name not in config and field_deserialization == deserialization:
            raise MissingParameter(
                param_hint=f"'{option} {field_name}={example}'", param_type="option"
            )


def validate_properties(config: Properties, valid_properties: Sequence[str]) -> None:
    if [property_name for property_name in config if property_name not in valid_properties]:
        raise BadParameter(message=f"Valid properties: {list(valid_properties)}.")


def normalize_choices(
    config: Properties,
    properties: Sequence[str],
    choices: Sequence[str],
    label: str,
) -> dict[str, str]:
    normalized = dict(config)
    for property_name in properties:
        if property_name not in normalized:
            continue
        value = normalized[property_name].lower().replace("_", "-")
        if value not in choices:
            raise BadParameter(message=f"{label} should be one of {list(choices)}.")
        normalized[property_name] = value
    return normalized


def validate_field_scope(
    config: Properties,
    property_name: str,
    deserialization: Format,
    key_deserialization: Format,
    value_deserialization: Format,
    option: str,
) -> None:
    if f"key.{property_name}" in config and key_deserialization != deserialization:
        raise BadParameter(f"{option} key.{property_name} requires '-k {deserialization}'.")
    if f"value.{property_name}" in config and value_deserialization != deserialization:
        raise BadParameter(f"{option} value.{property_name} requires '-v {deserialization}'.")


def validate_file(file_path: str, param_hint: str) -> None:
    path = Path(file_path).expanduser()
    if not path.exists():
        raise BadParameter(f"File {file_path!r} should exist.", param_hint=param_hint)

    if path.is_dir():
        raise BadParameter(f"Path {file_path!r} is a directory.", param_hint=param_hint)


def check_schema_files(
    config: Properties,
    option: str,
    load: Callable[[str], Any],
    fields: Sequence[str] = ("value", "key"),
) -> None:
    """Read each field's schema file now, so a bad one fails before the TUI opens."""
    for field_name in fields:
        if field_name in config:
            param_hint = f"'{option} {field_name}'"
            validate_file(config[field_name], param_hint)
            try:
                load(config[field_name])
            except SchemaError as ex:
                raise BadParameter(str(ex), param_hint=param_hint) from ex


def normalize_registry(
    registry_config: Properties,
    key_deserialization: Format,
    value_deserialization: Format,
) -> tuple[dict[str, str], ApicurioConfig | None]:
    """Return the normalized properties and, for Apicurio, its parsed configuration."""
    if not registry_config:
        return {}, None

    require_usage(type(key_deserialization).REGISTRY, key_deserialization, value_deserialization)
    provider = registry_config.get("provider", CONFLUENT_OPTION).lower()
    if provider not in REGISTRY_PROVIDERS:
        raise BadParameter(
            message=f"Registry provider should be one of {list(REGISTRY_PROVIDERS)}.",
            param_hint="'--registry provider'",
        )

    normalized = dict(registry_config)
    if "provider" in normalized:
        normalized["provider"] = provider
    apicurio_properties = [key for key in normalized if key.startswith(APICURIO_PREFIX)]
    if provider == CONFLUENT_OPTION and apicurio_properties:
        raise BadParameter(
            message=f"apicurio.registry.* properties require provider={APICURIO_OPTION}.",
            param_hint="'--registry'",
        )
    if provider != APICURIO_OPTION:
        return normalized, None

    try:
        return normalized, ApicurioConfig.from_dict(normalized)
    except (ApicurioRegistryError, OSError, ValueError) as ex:
        raise BadParameter(message=str(ex), param_hint="'--registry'") from ex


def normalize_producer_registry(
    registry_config: Properties,
    key_serialization: Serialization,
    value_serialization: Serialization,
) -> tuple[dict[str, str], ApicurioConfig | None, set[str]]:
    """Validate the client properties and each Registry field's schema selection.

    Also return the fields that register their schema.
    """
    client_config, selection = split_registry_config(registry_config)
    normalized, apicurio = normalize_registry(client_config, key_serialization, value_serialization)
    registering: set[str] = set()
    if not selection:
        return normalized, apicurio, registering
    require_usage(Serialization.REGISTRY, key_serialization, value_serialization)
    provider = normalized.get("provider", CONFLUENT_OPTION)
    for flag, field, serialization in (
        ("-k", MessageField.KEY, key_serialization),
        ("-v", MessageField.VALUE, value_serialization),
    ):
        prefix = f"{field.name.lower()}."
        if serialization != Serialization.REGISTRY:
            scoped = next((name for name in selection if name.startswith(prefix)), None)
            if scoped is not None:
                raise BadParameter(f"--registry {scoped} requires '{flag} registry'.")
            continue
        try:
            field_selection = SchemaSelection.from_config(selection, provider, field)
        except ValueError as ex:
            raise BadParameter(message=str(ex), param_hint="'--registry'") from ex
        if field_selection.auto_register:
            registering.add(field.name.lower())
    return normalized | selection, apicurio, registering


def normalize_bytes(
    bytes_config: Properties,
    key_deserialization: Format,
    value_deserialization: Format,
) -> dict[str, str]:
    if not bytes_config:
        return {}

    validate_properties(bytes_config, BYTES_CONFIGS)
    normalized = normalize_choices(bytes_config, BYTES_CONFIGS, BYTES_ENCODINGS, "Bytes encoding")
    kind = type(key_deserialization)
    require_usage(kind.BYTES, key_deserialization, value_deserialization)
    validate_field_scope(
        normalized,
        "encoding",
        kind.BYTES,
        key_deserialization,
        value_deserialization,
        "--bytes",
    )
    return normalized


def normalize_fallback(fallback_config: Properties) -> dict[str, str]:
    validate_properties(fallback_config, FALLBACK_CONFIGS)
    return normalize_choices(
        fallback_config, FALLBACK_CONFIGS, BYTES_ENCODINGS, "Fallback encoding"
    )


def normalize_json(
    json_config: Properties,
    key_deserialization: Format,
    value_deserialization: Format,
    valid_properties: Sequence[str],
) -> dict[str, str]:
    """Validate framing and the optional key and value JSON Schema files."""
    if not json_config:
        return {}

    validate_properties(json_config, valid_properties)
    normalized = normalize_choices(
        json_config, FRAMING_CONFIGS, DESERIALIZER_FRAMINGS, "JSON framing"
    )
    kind = type(key_deserialization)
    require_usage(kind.JSON, key_deserialization, value_deserialization)
    validate_field_scope(
        normalized, "framing", kind.JSON, key_deserialization, value_deserialization, "--json"
    )
    validate_schema_scope(
        normalized, kind.JSON, key_deserialization, value_deserialization, "--json"
    )
    check_schema_files(normalized, "--json", load_json_schema)
    return normalized


def validate_schema_scope(
    config: Properties,
    serialization: Format,
    key_serialization: Format,
    value_serialization: Format,
    option: str,
) -> None:
    """A field's schema file applies only when that field uses the format."""
    if "key" in config and key_serialization != serialization:
        raise BadParameter(f"{option} key requires '-k {serialization}'.")
    if "value" in config and value_serialization != serialization:
        raise BadParameter(f"{option} value requires '-v {serialization}'.")


def normalize_avro(
    avro_config: Properties,
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
) -> dict[str, str]:
    if not avro_config:
        return {}

    validate_properties(avro_config, AVRO_DESERIALIZER_CONFIGS)
    normalized = normalize_choices(
        avro_config, FRAMING_CONFIGS, DESERIALIZER_FRAMINGS, "Avro framing"
    )
    require_usage(Deserialization.AVRO, key_deserialization, value_deserialization)
    require_field_properties(
        normalized,
        Deserialization.AVRO,
        key_deserialization,
        value_deserialization,
        "--avro",
        "my-schema.avsc",
    )
    for field_name in ("value", "key"):
        if field_name in normalized:
            validate_file(normalized[field_name], f"'--avro {field_name}'")
    validate_field_scope(
        normalized,
        "framing",
        Deserialization.AVRO,
        key_deserialization,
        value_deserialization,
        "--avro",
    )
    return normalized


def normalize_protobuf(
    protobuf_config: Properties,
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
) -> dict[str, str]:
    if not protobuf_config:
        return {}

    validate_properties(protobuf_config, PROTOBUF_DESERIALIZER_CONFIGS)
    normalized = normalize_choices(
        protobuf_config, FRAMING_CONFIGS, DESERIALIZER_FRAMINGS, "Protobuf framing"
    )
    require_usage(Deserialization.PROTOBUF, key_deserialization, value_deserialization)
    require_protobuf_schema(normalized)
    require_field_properties(
        normalized,
        Deserialization.PROTOBUF,
        key_deserialization,
        value_deserialization,
        "--protobuf",
        "MyMessage",
    )
    check_protobuf_messages(normalized)
    validate_field_scope(
        normalized,
        "framing",
        Deserialization.PROTOBUF,
        key_deserialization,
        value_deserialization,
        "--protobuf",
    )
    return normalized


def normalize_producer_avro(
    avro_config: Properties,
    key_serialization: Serialization,
    value_serialization: Serialization,
) -> dict[str, str]:
    if not avro_config:
        return {}

    validate_properties(avro_config, AVRO_SERIALIZER_CONFIGS)
    normalized = dict(avro_config)
    formats = (key_serialization, value_serialization)
    require_usage(Serialization.AVRO, *formats)
    require_field_properties(normalized, Serialization.AVRO, *formats, "--avro", "my-schema.avsc")
    validate_schema_scope(normalized, Serialization.AVRO, *formats, "--avro")
    check_schema_files(normalized, "--avro", load_avro_schema)
    return normalized


def normalize_producer_protobuf(
    protobuf_config: Properties,
    key_serialization: Serialization,
    value_serialization: Serialization,
) -> dict[str, str]:
    if not protobuf_config:
        return {}

    validate_properties(protobuf_config, PROTOBUF_SERIALIZER_CONFIGS)
    normalized = dict(protobuf_config)
    formats = (key_serialization, value_serialization)
    require_usage(Serialization.PROTOBUF, *formats)
    require_protobuf_schema(normalized)
    require_field_properties(
        normalized, Serialization.PROTOBUF, *formats, "--protobuf", "MyMessage"
    )
    validate_schema_scope(normalized, Serialization.PROTOBUF, *formats, "--protobuf")
    check_protobuf_messages(normalized)
    return normalized


def require_protobuf_schema(config: Properties) -> None:
    """Exactly one of descriptor= (a descriptor set) or source= (a .proto file)."""
    given = [name for name in PROTOBUF_SCHEMA_CONFIGS if name in config]
    if not given:
        raise MissingParameter(
            param_hint="'--protobuf descriptor=my-descriptor' or '--protobuf source=my.proto'",
            param_type="option",
        )
    if len(given) > 1:
        raise BadParameter("Use either descriptor or source, not both.", param_hint="'--protobuf'")
    validate_file(config[given[0]], f"'--protobuf {given[0]}'")


def check_protobuf_messages(config: Properties) -> None:
    """Compile or read the schema now and find each field's message."""
    for field_name in ("value", "key"):
        if field_name in config:
            try:
                local_message_class(config, config[field_name])
            except SchemaError as ex:
                raise BadParameter(str(ex), param_hint=f"'--protobuf {field_name}'") from ex
