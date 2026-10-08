from typing import Any

from confluent_kafka.serialization import MessageField

from kaskade.apicurio import ApicurioConfig
from kaskade.configs import APICURIO_OPTION, CONFLUENT_OPTION, REGISTRY_PROVIDERS
from kaskade.deserializers.apicurio import ApicurioRegistryDeserializer
from kaskade.deserializers.base import (
    Deserialization,
    DeserializationError,
    DeserializationResult,
    Deserializer,
)
from kaskade.deserializers.confluent import ConfluentRegistryDeserializer
from kaskade.deserializers.local import AvroDeserializer, JsonDeserializer, ProtobufDeserializer
from kaskade.deserializers.primitives import (
    BooleanDeserializer,
    DefaultDeserializer,
    DoubleDeserializer,
    FloatDeserializer,
    IntegerDeserializer,
    LongDeserializer,
    StringDeserializer,
)


class RegistryDeserializer(Deserializer):
    """Delegates to the deserializer of the configured Registry provider.

    Pass ``apicurio_config`` when the CLI already parsed it, so its TLS material
    is loaded once.
    """

    def __init__(
        self, registry_config: dict[str, str], apicurio_config: ApicurioConfig | None = None
    ):
        provider = registry_config.get("provider", CONFLUENT_OPTION).lower()
        self._backend: ConfluentRegistryDeserializer | ApicurioRegistryDeserializer
        if provider == CONFLUENT_OPTION:
            self._backend = ConfluentRegistryDeserializer(registry_config)
        elif provider == APICURIO_OPTION:
            self._backend = ApicurioRegistryDeserializer(
                apicurio_config or ApicurioConfig.from_dict(registry_config)
            )
        else:
            raise DeserializationError(
                f"Unsupported registry provider: {provider}; "
                f"expected one of {list(REGISTRY_PROVIDERS)}"
            )

    def deserialize(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> Any:
        return self._backend.deserialize(data, topic, context)

    def deserialize_with_metadata(
        self, data: bytes, topic: str | None = None, context: MessageField = MessageField.NONE
    ) -> DeserializationResult:
        return self._backend.deserialize_with_metadata(data, topic, context)

    def close(self) -> None:
        self._backend.close()


class DeserializerPool:
    def __init__(
        self,
        registry_config: dict[str, str] | None = None,
        protobuf_config: dict[str, str] | None = None,
        avro_config: dict[str, str] | None = None,
        json_config: dict[str, str] | None = None,
        apicurio_config: ApicurioConfig | None = None,
    ):
        self.registry_deserializer: RegistryDeserializer | None = None
        self.protobuf_deserializer: ProtobufDeserializer | None = None
        self.avro_deserializer: AvroDeserializer | None = None

        if registry_config:
            self.registry_deserializer = RegistryDeserializer(registry_config, apicurio_config)

        if avro_config:
            self.avro_deserializer = AvroDeserializer(avro_config)

        if protobuf_config:
            self.protobuf_deserializer = ProtobufDeserializer(protobuf_config)

        self.string_deserializer = StringDeserializer()
        self.json_deserializer = JsonDeserializer(json_config)
        self.integer_deserializer = IntegerDeserializer()
        self.float_deserializer = FloatDeserializer()
        self.double_deserializer = DoubleDeserializer()
        self.boolean_deserializer = BooleanDeserializer()
        self.long_deserializer = LongDeserializer()
        self.default_deserializer = DefaultDeserializer()
        self._deserializers: dict[Deserialization, Deserializer | None] = {
            Deserialization.BYTES: self.default_deserializer,
            Deserialization.STRING: self.string_deserializer,
            Deserialization.JSON: self.json_deserializer,
            Deserialization.INTEGER: self.integer_deserializer,
            Deserialization.LONG: self.long_deserializer,
            Deserialization.DOUBLE: self.double_deserializer,
            Deserialization.FLOAT: self.float_deserializer,
            Deserialization.BOOLEAN: self.boolean_deserializer,
            Deserialization.REGISTRY: self.registry_deserializer,
            Deserialization.AVRO: self.avro_deserializer,
            Deserialization.PROTOBUF: self.protobuf_deserializer,
        }

    def get(self, deserialization_format: Deserialization) -> Deserializer:
        try:
            deserializer = self._deserializers[deserialization_format]
        except KeyError as ex:
            raise DeserializationError(
                f"Deserializer not registered: {deserialization_format}"
            ) from ex
        if deserializer is None:
            configured_name = {
                Deserialization.REGISTRY: "Schema Registry",
                Deserialization.AVRO: "Avro",
                Deserialization.PROTOBUF: "Protobuf",
            }[deserialization_format]
            raise DeserializationError(f"{configured_name} is not configured")
        return deserializer

    def close(self) -> None:
        if self.registry_deserializer is not None:
            self.registry_deserializer.close()
