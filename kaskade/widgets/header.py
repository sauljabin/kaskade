from rich.columns import Columns
from rich.table import Table
from textual.keys import Keys
from textual.widget import Widget

from kaskade.renderables.kaskade_name import KaskadeName
from kaskade.renderables.shortcuts import Shortcuts


class Header(Widget):
    kafka_version = "unknown"
    total_brokers = 0
    protocol = "unknown"
    has_schemas = False

    def on_mount(self):
        self.layout_size = 6

    def render(self):
        kafka_info = Table(box=None, expand=False)
        kafka_info.add_column(style="bold blue")
        kafka_info.add_column()

        kafka_info.add_row("kafka:", self.kafka_version)
        kafka_info.add_row("brokers:", str(self.total_brokers))
        kafka_info.add_row("schemas:", "yes" if self.has_schemas else "no")
        kafka_info.add_row(
            "protocol:", self.protocol.lower() if self.protocol else "plain"
        )

        return Columns([KaskadeName(), kafka_info, Shortcuts()], padding=3)
