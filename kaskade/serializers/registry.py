"""Registry serializers that look up a registered schema and frame records with its ID.

Kaskade encodes the records itself, the same way for Confluent and Apicurio, and
only looks up schemas: registering them is never done here.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from struct import Struct
from typing import Any

import httpx
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.error import SchemaRegistryError
from confluent_kafka.serialization import MessageField
from google.protobuf.descriptor import Descriptor
from google.protobuf.descriptor_pb2 import FileDescriptorProto
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message_factory import GetMessageClass

from kaskade import logger
from kaskade.apicurio import (
    APICURIO_ARTIFACT_GROUP_ID,
    APICURIO_ARTIFACT_ID,
    APICURIO_ARTIFACT_VERSION,
    APICURIO_AUTO_REGISTER,
    APICURIO_DEFAULT_GROUP,
    APICURIO_FIND_LATEST,
    APICURIO_LATEST_VERSION,
    ApicurioClient,
    ApicurioConfig,
    ApicurioRegistryError,
)
from kaskade.configs import (
    APICURIO_OPTION,
    AUTO_REGISTER_SCHEMAS,
    CONFLUENT_OPTION,
    PROTOBUF_MESSAGE,
    SCHEMA_REGISTRY_MAGIC_BYTE,
    USE_LATEST_VERSION,
    USE_SCHEMA_ID,
    SchemaType,
)
from kaskade.schemas import SchemaError
from kaskade.schemas.apicurio import ApicurioSchemas
from kaskade.schemas.confluent import ConfluentSchemas
from kaskade.schemas.json_schema import validation_error
from kaskade.schemas.protobuf import find_message, first_message
from kaskade.serializers.avro import encode_avro
from kaskade.serializers.base import (
    JsonDocumentSerializer,
    SchemaSummary,
    SerializationError,
    compact_json,
    parse_json,
)
from kaskade.serializers.protobuf import (
    apicurio_type_ref,
    confluent_message_indexes,
    encode_protobuf,
)

REGISTRY_HEADER = Struct(">bI")
FIELD_PREFIXES = ("key.", "value.")
SELECTION_PROPERTIES = {
    CONFLUENT_OPTION: (AUTO_REGISTER_SCHEMAS, USE_LATEST_VERSION, USE_SCHEMA_ID, PROTOBUF_MESSAGE),
    APICURIO_OPTION: (
        APICURIO_AUTO_REGISTER,
        APICURIO_FIND_LATEST,
        APICURIO_ARTIFACT_GROUP_ID,
        APICURIO_ARTIFACT_ID,
        APICURIO_ARTIFACT_VERSION,
        PROTOBUF_MESSAGE,
    ),
}
ALL_SELECTION_PROPERTIES = frozenset(
    name for names in SELECTION_PROPERTIES.values() for name in names
)
REGISTRY_EXCEPTIONS: tuple[type[Exception], ...] = (
    SchemaRegistryError,
    httpx.HTTPError,
    OSError,
    ValueError,
)
LOOKING_UP = "Looking up the schema"
NO_VERSION = "—"
Encoder = Callable[[Any], bytes]


def selection_property(name: str) -> str | None:
    """The schema-selection property `name` sets, globally or for one field, if any."""
    for prefix in ("", *FIELD_PREFIXES):
        base = name.removeprefix(prefix)
        if name.startswith(prefix) and base in ALL_SELECTION_PROPERTIES:
            return base
    return None


def split_registry_config(config: Mapping[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Separate the Registry client properties from the schema-selection properties."""
    client: dict[str, str] = {}
    selection: dict[str, str] = {}
    for name, value in config.items():
        (client if selection_property(name) is None else selection)[name] = value
    return client, selection


@dataclass(frozen=True)
class SchemaSelection:
    """How one field's registered schema is chosen, as the official serializers do."""

    schema_id: int | None = None
    group: str = APICURIO_DEFAULT_GROUP
    artifact: str | None = None
    version: str | None = None
    protobuf_message: str | None = None

    @classmethod
    def from_config(
        cls, selection: Mapping[str, str], provider: str, field: MessageField
    ) -> "SchemaSelection":
        """Validate the selection properties; scoped ones override global ones."""
        for name in selection:
            base = selection_property(name)
            if base is not None and base not in SELECTION_PROPERTIES[provider]:
                other = APICURIO_OPTION if provider == CONFLUENT_OPTION else CONFLUENT_OPTION
                raise ValueError(f"{name} requires provider={other}")

        def value(name: str) -> str | None:
            scoped = f"{field.name.lower()}.{name}"
            return selection.get(scoped, selection.get(name))

        if provider == CONFLUENT_OPTION:
            return cls._confluent(value)
        return cls._apicurio(value)

    @classmethod
    def _confluent(cls, value: Callable[[str], str | None]) -> "SchemaSelection":
        _refuse_registration(AUTO_REGISTER_SCHEMAS, value(AUTO_REGISTER_SCHEMAS))
        if _boolean(USE_LATEST_VERSION, value(USE_LATEST_VERSION)) is False:
            raise ValueError(
                f"{USE_LATEST_VERSION}=false needs a local schema; Kaskade uses the latest "
                f"version or {USE_SCHEMA_ID}"
            )
        return cls(
            schema_id=_schema_id(value(USE_SCHEMA_ID)),
            protobuf_message=value(PROTOBUF_MESSAGE),
        )

    @classmethod
    def _apicurio(cls, value: Callable[[str], str | None]) -> "SchemaSelection":
        _refuse_registration(APICURIO_AUTO_REGISTER, value(APICURIO_AUTO_REGISTER))
        version = value(APICURIO_ARTIFACT_VERSION)
        if _boolean(APICURIO_FIND_LATEST, value(APICURIO_FIND_LATEST)) is False and not version:
            raise ValueError(
                f"{APICURIO_FIND_LATEST}=false needs a local schema; set "
                f"{APICURIO_ARTIFACT_VERSION} or let Kaskade use the latest version"
            )
        for name in (APICURIO_ARTIFACT_GROUP_ID, APICURIO_ARTIFACT_ID, APICURIO_ARTIFACT_VERSION):
            if value(name) == "":
                raise ValueError(f"{name} must not be empty")
        return cls(
            group=value(APICURIO_ARTIFACT_GROUP_ID) or APICURIO_DEFAULT_GROUP,
            artifact=value(APICURIO_ARTIFACT_ID),
            version=version,
            protobuf_message=value(PROTOBUF_MESSAGE),
        )


def _boolean(name: str, value: str | None) -> bool | None:
    if value is None:
        return None
    if value.lower() not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value.lower() == "true"


def _refuse_registration(name: str, value: str | None) -> None:
    if _boolean(name, value):
        raise ValueError(
            f"{name}=true isn't supported yet; Kaskade only looks up registered schemas"
        )


def _schema_id(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        schema_id = int(value)
    except ValueError:
        schema_id = 0
    if schema_id <= 0:
        raise ValueError(f"{USE_SCHEMA_ID} must be a positive integer")
    return schema_id


@dataclass(frozen=True)
class ResolvedSchema:
    summary: SchemaSummary
    encode: Encoder


def encode_json(validator: Any, content: Any) -> bytes:
    error = validation_error(validator, content)
    if error is not None:
        raise SerializationError(error)
    return compact_json(content)


def _framed(header: bytes, encode: Encoder, content: Any) -> bytes:
    return header + encode(content)


def _with_prefix(prefix: bytes, encode: Encoder, content: Any) -> bytes:
    return prefix + encode(content)


def _protobuf_message(
    pool: DescriptorPool, root: FileDescriptorProto, name: str | None
) -> Descriptor:
    return first_message(pool, root) if name is None else find_message(pool, root, name)


def _subject(topic: str, field: MessageField) -> str:
    return f"{topic}-{field.name.lower()}"


class ConfluentSchemaResolver:
    """TopicNameStrategy subjects, encoded with the latest version or use.schema.id."""

    def __init__(self, registry_config: Mapping[str, str]) -> None:
        client_config = {key: value for key, value in registry_config.items() if key != "provider"}
        self.client = SchemaRegistryClient(client_config)
        self.schemas = ConfluentSchemas(self.client)

    def resolve(
        self, topic: str, field: MessageField, selection: SchemaSelection
    ) -> ResolvedSchema:
        subject = _subject(topic, field)
        if selection.schema_id is None:
            registered = self.client.get_latest_version(subject)
            if registered.schema_id is None:
                raise SchemaError(f"Subject {subject} has no schema ID")
            schema_id, version = registered.schema_id, str(registered.version)
        else:
            schema_id, version = selection.schema_id, self._version(selection.schema_id, subject)
        schema_type = self.schemas.schema_type(schema_id)
        encode = self._encoder(schema_id, schema_type, selection)
        header = REGISTRY_HEADER.pack(SCHEMA_REGISTRY_MAGIC_BYTE, schema_id)
        return ResolvedSchema(
            SchemaSummary(subject, version, schema_id, schema_type.value),
            partial(_framed, header, encode),
        )

    def _version(self, schema_id: int, subject: str) -> str:
        for registration in self.client.get_schema_versions(schema_id):
            if registration.subject == subject:
                return str(registration.version)
        return NO_VERSION

    def _encoder(
        self, schema_id: int, schema_type: SchemaType, selection: SchemaSelection
    ) -> Encoder:
        if schema_type == SchemaType.AVRO:
            return partial(encode_avro, self.schemas.avro_schema(schema_id))
        if schema_type == SchemaType.JSON:
            return partial(encode_json, self.schemas.json_validator(schema_id))
        root, pool = self.schemas.protobuf_descriptors(schema_id)
        descriptor = _protobuf_message(pool, root, selection.protobuf_message)
        return partial(
            _with_prefix,
            confluent_message_indexes(root, descriptor),
            partial(encode_protobuf, GetMessageClass(descriptor)),
        )

    def close(self) -> None:
        self.client.close()


class ApicurioSchemaResolver:
    """TopicIdStrategy artifacts, encoded with the latest or a chosen version."""

    def __init__(self, config: ApicurioConfig) -> None:
        self.client = ApicurioClient(config)
        self.schemas = ApicurioSchemas(self.client)

    def resolve(
        self, topic: str, field: MessageField, selection: SchemaSelection
    ) -> ResolvedSchema:
        artifact_id = selection.artifact or _subject(topic, field)
        name = (
            artifact_id
            if selection.group == APICURIO_DEFAULT_GROUP
            else f"{selection.group}/{artifact_id}"
        )
        try:
            version = self.client.get_version(
                selection.group, artifact_id, selection.version or APICURIO_LATEST_VERSION
            )
        except ApicurioRegistryError as ex:
            cause = ex.__cause__
            if isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code == 404:
                raise SchemaError(f"Apicurio artifact {name} has no such version") from ex
            raise
        use_content_id = self.client.config.use_id == "contentId"
        schema_id = version.content_id if use_content_id else version.global_id
        artifact = self.client.get_artifact(schema_id)
        if artifact.type == SchemaType.AVRO:
            encode = partial(encode_avro, self.schemas.avro_schema(artifact))
        elif artifact.type == SchemaType.JSON:
            encode = partial(encode_json, self.schemas.json_validator(artifact))
        else:
            root, pool = self.schemas.protobuf_descriptors(artifact)
            descriptor = _protobuf_message(pool, root, selection.protobuf_message)
            encode = partial(
                _with_prefix,
                apicurio_type_ref(descriptor),
                partial(encode_protobuf, GetMessageClass(descriptor)),
            )
        header = REGISTRY_HEADER.pack(SCHEMA_REGISTRY_MAGIC_BYTE, schema_id)
        return ResolvedSchema(
            SchemaSummary(name, version.version, schema_id, artifact.type),
            partial(_framed, header, encode),
        )

    def close(self) -> None:
        self.client.close()


SchemaResolver = ConfluentSchemaResolver | ApicurioSchemaResolver


def schema_resolver(
    registry_config: Mapping[str, str], apicurio_config: ApicurioConfig | None = None
) -> SchemaResolver:
    client_config, _ = split_registry_config(registry_config)
    if client_config.get("provider", CONFLUENT_OPTION).lower() == APICURIO_OPTION:
        return ApicurioSchemaResolver(apicurio_config or ApicurioConfig.from_dict(client_config))
    return ConfluentSchemaResolver(client_config)


class RegistrySerializer(JsonDocumentSerializer):
    """Encodes one field with its registered schema once resolve() finds it."""

    def __init__(
        self,
        resolver: SchemaResolver,
        topic: str,
        field: MessageField,
        selection: SchemaSelection,
    ) -> None:
        self._resolver = resolver
        self._topic = topic
        self._field = field
        self._selection = selection
        self._resolved: ResolvedSchema | None = None
        self._problem: str | None = None

    @property
    def label(self) -> str:  # type: ignore[override]
        if self._resolved is None:
            return "REGISTRY"
        return f"REGISTRY · {self._resolved.summary.type}"

    @property
    def needs_schema(self) -> bool:
        return self._resolved is None

    @property
    def schema(self) -> SchemaSummary | None:
        return None if self._resolved is None else self._resolved.summary

    def resolve(self) -> None:
        try:
            self._resolved = self._resolver.resolve(self._topic, self._field, self._selection)
        except REGISTRY_EXCEPTIONS as ex:
            self._problem = registry_problem(ex)
            logger.warning(
                "schema lookup failed topic=%s field=%s error=%s",
                self._topic,
                self._field.name,
                self._problem,
            )
        else:
            self._problem = None

    def serialize(self, text: str) -> bytes:
        content = parse_json(text)
        if self._resolved is None:
            raise SerializationError(self._problem or LOOKING_UP)
        return self._resolved.encode(content)


def registry_problem(ex: Exception) -> str:
    if isinstance(ex, SchemaRegistryError):
        return f"Schema Registry error: {ex.error_message}"
    return f"Schema lookup failed: {ex}"
