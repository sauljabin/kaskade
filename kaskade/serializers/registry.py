"""Registry serializers that look up or register a schema and frame records with its ID.

Kaskade encodes the records itself, the same way for Confluent and Apicurio. It
registers a local schema only when auto-registration is enabled for the field.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from struct import Struct
from typing import Any

import httpx
from confluent_kafka.schema_registry import Schema, SchemaReference, SchemaRegistryClient
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
    ApicurioReference,
    ApicurioRegistryError,
    ApicurioVersion,
)
from kaskade.configs import (
    APICURIO_OPTION,
    AUTO_REGISTER_SCHEMAS,
    CONFLUENT_OPTION,
    NORMALIZE_SCHEMAS,
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
from kaskade.schemas.registration import SchemaDocument
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
    CONFLUENT_OPTION: (
        AUTO_REGISTER_SCHEMAS,
        NORMALIZE_SCHEMAS,
        USE_LATEST_VERSION,
        USE_SCHEMA_ID,
        PROTOBUF_MESSAGE,
    ),
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
REGISTERING = "Registering the schema"
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
    """How one field's schema is chosen or registered, as the official serializers do."""

    schema_id: int | None = None
    group: str = APICURIO_DEFAULT_GROUP
    artifact: str | None = None
    version: str | None = None
    protobuf_message: str | None = None
    auto_register: bool = False
    normalize: bool = False

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
        auto_register = bool(_boolean(AUTO_REGISTER_SCHEMAS, value(AUTO_REGISTER_SCHEMAS)))
        use_latest = _boolean(USE_LATEST_VERSION, value(USE_LATEST_VERSION))
        schema_id = _schema_id(value(USE_SCHEMA_ID))
        if auto_register:
            # The official serializers refuse these combinations too.
            _refuse_with_registration(AUTO_REGISTER_SCHEMAS, USE_LATEST_VERSION, use_latest)
            _refuse_with_registration(AUTO_REGISTER_SCHEMAS, USE_SCHEMA_ID, schema_id)
        elif use_latest is False:
            raise ValueError(
                f"{USE_LATEST_VERSION}=false needs {AUTO_REGISTER_SCHEMAS}=true and a schema "
                f"file; otherwise Kaskade uses the latest version or {USE_SCHEMA_ID}"
            )
        return cls(
            schema_id=schema_id,
            protobuf_message=value(PROTOBUF_MESSAGE),
            auto_register=auto_register,
            normalize=bool(_boolean(NORMALIZE_SCHEMAS, value(NORMALIZE_SCHEMAS))),
        )

    @classmethod
    def _apicurio(cls, value: Callable[[str], str | None]) -> "SchemaSelection":
        auto_register = bool(_boolean(APICURIO_AUTO_REGISTER, value(APICURIO_AUTO_REGISTER)))
        find_latest = _boolean(APICURIO_FIND_LATEST, value(APICURIO_FIND_LATEST))
        version = value(APICURIO_ARTIFACT_VERSION)
        for name in (APICURIO_ARTIFACT_GROUP_ID, APICURIO_ARTIFACT_ID, APICURIO_ARTIFACT_VERSION):
            if value(name) == "":
                raise ValueError(f"{name} must not be empty")
        if auto_register:
            _refuse_with_registration(APICURIO_AUTO_REGISTER, APICURIO_FIND_LATEST, find_latest)
            _refuse_with_registration(APICURIO_AUTO_REGISTER, APICURIO_ARTIFACT_VERSION, version)
        elif find_latest is False and not version:
            raise ValueError(
                f"{APICURIO_FIND_LATEST}=false needs {APICURIO_ARTIFACT_VERSION}, or "
                f"{APICURIO_AUTO_REGISTER}=true and a schema file"
            )
        return cls(
            group=value(APICURIO_ARTIFACT_GROUP_ID) or APICURIO_DEFAULT_GROUP,
            artifact=value(APICURIO_ARTIFACT_ID),
            version=version,
            protobuf_message=value(PROTOBUF_MESSAGE),
            auto_register=auto_register,
        )


def _boolean(name: str, value: str | None) -> bool | None:
    if value is None:
        return None
    if value.lower() not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value.lower() == "true"


def _refuse_with_registration(registration: str, name: str, value: object) -> None:
    if value is not None and value is not False:
        raise ValueError(f"{registration}=true can't be combined with {name}")


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
    """TopicNameStrategy subjects: registered, the latest version, or use.schema.id."""

    def __init__(self, registry_config: Mapping[str, str]) -> None:
        client_config = {key: value for key, value in registry_config.items() if key != "provider"}
        self.client = SchemaRegistryClient(client_config)
        self.schemas = ConfluentSchemas(self.client)
        self._registered: dict[tuple[str, SchemaDocument], tuple[int, int]] = {}

    def resolve(
        self,
        topic: str,
        field: MessageField,
        selection: SchemaSelection,
        document: SchemaDocument | None = None,
    ) -> ResolvedSchema:
        subject = _subject(topic, field)
        if document is not None:
            schema_id, registered_version = self._register(subject, document, selection.normalize)
            version = str(registered_version)
        elif selection.schema_id is None:
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

    def _register(self, subject: str, document: SchemaDocument, normalize: bool) -> tuple[int, int]:
        """Register references first, then the schema; identical content keeps its version."""
        cached = self._registered.get((subject, document))
        if cached is not None:
            return cached
        references = [
            SchemaReference(
                reference.name,
                reference.name,
                self._register(reference.name, reference.document, normalize)[1],
            )
            for reference in document.references
        ]
        schema = Schema(document.content, document.type.value, references)
        registered = self.client.register_schema_full_response(
            subject, schema, normalize_schemas=normalize
        )
        version = registered.version
        if version is None:
            version = self.client.lookup_schema(
                subject, schema, normalize_schemas=normalize
            ).version
        if registered.schema_id is None or version is None:
            raise SchemaError(f"Schema Registry returned no ID or version for {subject}")
        result = (registered.schema_id, version)
        self._registered[(subject, document)] = result
        return result

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
    """TopicIdStrategy artifacts: registered, the latest version, or a chosen one."""

    def __init__(self, config: ApicurioConfig) -> None:
        self.client = ApicurioClient(config)
        self.schemas = ApicurioSchemas(self.client)
        self._registered: dict[tuple[str, str, SchemaDocument], ApicurioVersion] = {}

    def resolve(
        self,
        topic: str,
        field: MessageField,
        selection: SchemaSelection,
        document: SchemaDocument | None = None,
    ) -> ResolvedSchema:
        artifact_id = selection.artifact or _subject(topic, field)
        name = (
            artifact_id
            if selection.group == APICURIO_DEFAULT_GROUP
            else f"{selection.group}/{artifact_id}"
        )
        if document is not None:
            version = self._register(selection.group, artifact_id, document)
        else:
            version = self._version(selection, artifact_id, name)
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

    def _version(self, selection: SchemaSelection, artifact_id: str, name: str) -> ApicurioVersion:
        try:
            return self.client.get_version(
                selection.group, artifact_id, selection.version or APICURIO_LATEST_VERSION
            )
        except ApicurioRegistryError as ex:
            if _status(ex) == 404:
                raise SchemaError(f"Apicurio artifact {name} has no such version") from ex
            raise

    def _register(self, group: str, artifact_id: str, document: SchemaDocument) -> ApicurioVersion:
        """Register references first, then the artifact, reusing versions with the same content."""
        cached = self._registered.get((group, artifact_id, document))
        if cached is not None:
            return cached
        references = tuple(
            ApicurioReference(
                name=reference.name,
                group=group,
                artifact=reference.name,
                version=self._register(group, reference.name, reference.document).version,
            )
            for reference in document.references
        )
        try:
            version = self.client.create_version(
                group, artifact_id, document.type.value, document.content, references
            )
        except ApicurioRegistryError as ex:
            if _status(ex) in {401, 403}:
                raise SchemaError(
                    f"Apicurio refused to register {artifact_id}; registering needs write access"
                ) from ex
            raise
        self._registered[(group, artifact_id, document)] = version
        return version

    def close(self) -> None:
        self.client.close()


SchemaResolver = ConfluentSchemaResolver | ApicurioSchemaResolver


def _status(ex: ApicurioRegistryError) -> int | None:
    cause = ex.__cause__
    return cause.response.status_code if isinstance(cause, httpx.HTTPStatusError) else None


def schema_resolver(
    registry_config: Mapping[str, str], apicurio_config: ApicurioConfig | None = None
) -> SchemaResolver:
    client_config, _ = split_registry_config(registry_config)
    if client_config.get("provider", CONFLUENT_OPTION).lower() == APICURIO_OPTION:
        return ApicurioSchemaResolver(apicurio_config or ApicurioConfig.from_dict(client_config))
    return ConfluentSchemaResolver(client_config)


class RegistrySerializer(JsonDocumentSerializer):
    """Encodes one field with its registered schema once resolve() finds or registers it."""

    def __init__(
        self,
        resolver: SchemaResolver,
        topic: str,
        field: MessageField,
        selection: SchemaSelection,
        document: SchemaDocument | None = None,
    ) -> None:
        self._resolver = resolver
        self._topic = topic
        self._field = field
        self._selection = selection
        self._document = document
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
            self._resolved = self._resolver.resolve(
                self._topic, self._field, self._selection, self._document
            )
        except REGISTRY_EXCEPTIONS as ex:
            self._problem = registry_problem(ex, registering=self._document is not None)
            logger.warning(
                "schema %s failed topic=%s field=%s error=%s",
                "registration" if self._document is not None else "lookup",
                self._topic,
                self._field.name,
                self._problem,
            )
        else:
            self._problem = None

    def serialize(self, text: str) -> bytes:
        content = parse_json(text)
        if self._resolved is None:
            pending = REGISTERING if self._document is not None else LOOKING_UP
            raise SerializationError(self._problem or pending)
        return self._resolved.encode(content)


def registry_problem(ex: Exception, *, registering: bool = False) -> str:
    if isinstance(ex, SchemaRegistryError):
        problem = f"Schema Registry error: {ex.error_message}"
        if registering and ex.http_status_code in {401, 403}:
            problem += "; registering needs write access to the subject"
        return problem
    return f"Schema {'registration' if registering else 'lookup'} failed: {ex}"
