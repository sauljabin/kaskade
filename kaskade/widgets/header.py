from rich.columns import Columns
from textual.widget import Widget

from kaskade.renderables.kafka_info import KafkaInfo
from kaskade.renderables.kaskade_name import KaskadeName
from kaskade.renderables.shortcuts import Shortcuts


class Header(Widget):
    kafka_version = "unknown"
    total_brokers = 0
    protocol = "unknown"
    has_schemas = False

    def on_mount(self) -> None:
        self.layout_size = 6
        self.kafka_version = self.app.cluster.version
        self.total_brokers = len(self.app.cluster.brokers)
        self.has_schemas = self.app.cluster.has_schemas
        self.protocol = self.app.cluster.protocol

    def render(self) -> Columns:
        kaskade_name = KaskadeName()
        kafka_info = KafkaInfo(
            kafka_version=self.kafka_version,
            total_brokers=self.total_brokers,
            has_schemas=self.has_schemas,
            protocol=self.protocol,
        )
        shortcuts = Shortcuts()
        return Columns([kaskade_name, kafka_info, shortcuts], padding=3)
