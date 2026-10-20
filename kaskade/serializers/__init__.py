"""Producer serializers that turn composer text into Kafka key and value bytes.

Encoding stays independent of the consumer deserializers; both share schema
loading and Registry lookups through `kaskade.schemas`.
"""

from kaskade.serializers.base import (
    SchemaSummary,
    Serialization,
    SerializationError,
    Serializer,
)
from kaskade.serializers.pool import SerializerPool
from kaskade.serializers.registry import (
    RegistrySerializer,
    SchemaSelection,
    selection_property,
    split_registry_config,
)

__all__ = [
    "RegistrySerializer",
    "SchemaSelection",
    "SchemaSummary",
    "Serialization",
    "SerializationError",
    "Serializer",
    "SerializerPool",
    "selection_property",
    "split_registry_config",
]
