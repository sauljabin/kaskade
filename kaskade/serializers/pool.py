from collections.abc import Callable, Mapping
from dataclasses import replace
from functools import partial

from confluent_kafka.serialization import MessageField

from kaskade.apicurio import ApicurioConfig
from kaskade.configs import APICURIO_OPTION, CONFLUENT_OPTION
from kaskade.deserializers import BytesEncoding
from kaskade.schemas import SchemaError
from kaskade.schemas.json_schema import load_json_schema
from kaskade.schemas.registration import (
    SchemaDocument,
    avro_document,
    json_document,
    protobuf_document,
)
from kaskade.serializers.base import Serialization, Serializer
from kaskade.serializers.local import AvroSerializer, ProtobufSerializer
from kaskade.serializers.primitives import (
    BooleanSerializer,
    BytesSerializer,
    FloatSerializer,
    IntegerSerializer,
    JsonSerializer,
    StringSerializer,
)
from kaskade.serializers.registry import (
    RegistrySerializer,
    SchemaResolver,
    SchemaSelection,
    schema_resolver,
    split_registry_config,
)

FIXED_SERIALIZERS: dict[Serialization, Callable[[], Serializer]] = {
    Serialization.STRING: StringSerializer,
    Serialization.BOOLEAN: BooleanSerializer,
    Serialization.INTEGER: partial(IntegerSerializer, ">i", "a 32-bit integer", 32, "INTEGER"),
    Serialization.LONG: partial(IntegerSerializer, ">q", "a 64-bit integer", 64, "LONG"),
    Serialization.FLOAT: partial(FloatSerializer, ">f", "a 32-bit float", "FLOAT"),
    Serialization.DOUBLE: partial(FloatSerializer, ">d", "a 64-bit float", "DOUBLE"),
}


class SerializerPool:
    """Builds the serializer each field uses from the producer's serialization options.

    Local schema files, including those a Registry field registers, are read when
    a serializer is first requested. Registry serializers share one client,
    created on first use, and contact the registry only when resolve() runs.
    """

    def __init__(
        self,
        topic: str = "",
        *,
        registry_config: Mapping[str, str] | None = None,
        apicurio_config: ApicurioConfig | None = None,
        protobuf_config: Mapping[str, str] | None = None,
        avro_config: Mapping[str, str] | None = None,
        json_config: Mapping[str, str] | None = None,
        bytes_config: Mapping[str, str] | None = None,
    ) -> None:
        self.topic = topic
        self.registry_config = dict(registry_config or {})
        self.apicurio_config = apicurio_config
        self.protobuf_config = dict(protobuf_config or {})
        self.avro_config = dict(avro_config or {})
        self.json_config = dict(json_config or {})
        self.bytes_config = dict(bytes_config or {})
        self._resolver: SchemaResolver | None = None

    def get(self, serialization: Serialization, field: MessageField) -> Serializer:
        """Build the field's serializer; a local schema file that can't be used raises."""
        fixed = FIXED_SERIALIZERS.get(serialization)
        if fixed is not None:
            return fixed()
        name = field.name.lower()
        match serialization:
            case Serialization.BYTES:
                return BytesSerializer(BytesEncoding.from_config(self.bytes_config, field))
            case Serialization.JSON if name in self.json_config:
                schema_path = self.json_config[name]
                return JsonSerializer(load_json_schema(schema_path), schema_path)
            case Serialization.AVRO:
                return AvroSerializer(self.avro_config[name])
            case Serialization.PROTOBUF:
                return ProtobufSerializer(self.protobuf_config, self.protobuf_config[name])
            case Serialization.REGISTRY:
                return self._registry_serializer(field)
        return JsonSerializer()

    def _registry_serializer(self, field: MessageField) -> RegistrySerializer:
        client_config, selection_config = split_registry_config(self.registry_config)
        provider = client_config.get("provider", CONFLUENT_OPTION).lower()
        selection = SchemaSelection.from_config(selection_config, provider, field)
        document = None
        if selection.auto_register:
            document, message = self._registration_document(field, provider)
            if message is not None:
                selection = replace(selection, protobuf_message=message)
        if self._resolver is None:
            self._resolver = schema_resolver(self.registry_config, self.apicurio_config)
        return RegistrySerializer(self._resolver, self.topic, field, selection, document)

    def _registration_document(
        self, field: MessageField, provider: str
    ) -> tuple[SchemaDocument, str | None]:
        """Read the field's local schema file to register, and its Protobuf message."""
        name = field.name.lower()
        if name in self.avro_config:
            return avro_document(self.avro_config[name]), None
        if name in self.json_config:
            return json_document(self.json_config[name]), None
        if name in self.protobuf_config:
            message = self.protobuf_config[name]
            document = protobuf_document(
                self.protobuf_config, message, as_source=provider == APICURIO_OPTION
            )
            return document, message
        raise SchemaError(f"Registering the {name} schema needs --avro, --json, or --protobuf")

    def close(self) -> None:
        if self._resolver is not None:
            self._resolver.close()
            self._resolver = None
