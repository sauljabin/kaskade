"""The Kaskade consumer application."""

from typing import Any

from textual.app import ComposeResult
from textual.widgets import Footer

from kaskade.app import KaskadeApp
from kaskade.consumer.records import ListRecords, new_consumer
from kaskade.deserializers import Deserialization, DeserializerPool
from kaskade.models import PartitionSelection
from kaskade.timeouts import TimeoutConfig
from kaskade.widgets import KaskadeHeader, kantrip_profile


class KaskadeConsumer(KaskadeApp):
    TITLE = "Kaskade Consumer"
    AUTO_FOCUS = "#records-table"

    def __init__(
        self,
        topic: str,
        kafka_config: dict[str, Any],
        registry_config: dict[str, str],
        protobuf_config: dict[str, str],
        avro_config: dict[str, str],
        key_deserialization: Deserialization,
        value_deserialization: Deserialization,
        *,
        bytes_config: dict[str, str] | None = None,
        fallback_config: dict[str, str] | None = None,
        json_config: dict[str, str] | None = None,
        partitions: tuple[PartitionSelection, ...] = (),
        timeouts: TimeoutConfig | None = None,
    ):
        super().__init__()
        self.topic = topic
        self.kafka_config = kafka_config
        self.registry_config = registry_config
        self.protobuf_config = protobuf_config
        self.avro_config = avro_config
        self.bytes_config = bytes_config or {}
        self.fallback_config = fallback_config or {}
        self.json_config = json_config or {}
        self.key_deserialization = key_deserialization
        self.value_deserialization = value_deserialization
        self.partitions = partitions
        self.timeouts = timeouts or TimeoutConfig()
        self.deserializer_factory = DeserializerPool(
            self.registry_config,
            self.protobuf_config,
            self.avro_config,
            self.json_config,
        )
        self.consumer = new_consumer(
            self.topic,
            self.kafka_config,
            self.deserializer_factory,
            self.key_deserialization,
            self.value_deserialization,
            bytes_config=self.bytes_config,
            fallback_config=self.fallback_config,
            partitions=self.partitions,
            timeouts=self.timeouts,
        )
        try:
            self.consumer.start()
        except Exception:
            self.consumer.close()
            raise

    def compose(self) -> ComposeResult:
        yield KaskadeHeader(self.kafka_config, profile=kantrip_profile())
        yield ListRecords(
            self.topic,
            self.kafka_config,
            self.deserializer_factory,
            self.key_deserialization,
            self.value_deserialization,
            bytes_config=self.bytes_config,
            fallback_config=self.fallback_config,
            partitions=self.partitions,
            consumer=self.consumer,
            timeouts=self.timeouts,
        )
        yield Footer(compact=True)
