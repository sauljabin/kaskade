"""Kafka key, value, and header deserializers."""

from kaskade.deserializers.apicurio import ApicurioRegistryDeserializer
from kaskade.deserializers.base import (
    DESERIALIZATION_EXCEPTIONS,
    SCHEMA_METADATA_EXCEPTIONS,
    ApicurioRegistrySchema,
    BytesEncoding,
    Deserialization,
    DeserializationError,
    DeserializationResult,
    Deserializer,
    RegistrySchema,
)
from kaskade.deserializers.confluent import ConfluentRegistryDeserializer
from kaskade.deserializers.local import AvroDeserializer, JsonDeserializer, ProtobufDeserializer
from kaskade.deserializers.pool import DeserializerPool, RegistryDeserializer
from kaskade.deserializers.primitives import (
    BooleanDeserializer,
    DefaultDeserializer,
    DoubleDeserializer,
    FloatDeserializer,
    IntegerDeserializer,
    LongDeserializer,
    StringDeserializer,
    StructDeserializer,
)

__all__ = [
    "DESERIALIZATION_EXCEPTIONS",
    "SCHEMA_METADATA_EXCEPTIONS",
    "ApicurioRegistryDeserializer",
    "ApicurioRegistrySchema",
    "AvroDeserializer",
    "BooleanDeserializer",
    "BytesEncoding",
    "ConfluentRegistryDeserializer",
    "DefaultDeserializer",
    "Deserialization",
    "DeserializationError",
    "DeserializationResult",
    "Deserializer",
    "DeserializerPool",
    "DoubleDeserializer",
    "FloatDeserializer",
    "IntegerDeserializer",
    "JsonDeserializer",
    "LongDeserializer",
    "ProtobufDeserializer",
    "RegistryDeserializer",
    "RegistrySchema",
    "StringDeserializer",
    "StructDeserializer",
]
