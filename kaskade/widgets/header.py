from rich.columns import Columns
from textual.widget import Widget

from kaskade.renderables.kafka_info import KafkaInfo
from kaskade.renderables.kaskade_name import KaskadeName
from kaskade.renderables.shortcuts_header import ShortcutsHeader


class Header(Widget):
    def on_mount(self) -> None:
        self.layout_size = 6

    def render(self) -> Columns:
        cluster = self.app.cluster
        kafka_info = KafkaInfo(
            kafka_version=cluster.version,
            total_brokers=len(cluster.brokers),
            has_schemas=cluster.has_schemas,
            protocol=cluster.protocol,
        )
        kaskade_name = KaskadeName()
        shortcuts = ShortcutsHeader()
        return Columns([kaskade_name, kafka_info, shortcuts], padding=3)
