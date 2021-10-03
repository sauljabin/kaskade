from rich.columns import Columns
from rich.table import Table
from textual.keys import Keys
from textual.widget import Widget

from kaskade.renderables.kaskade_name import KaskadeName


class Header(Widget):
    kafka_version = "unknown"
    total_brokers = 0
    protocol = "unknown"
    has_schemas = False

    def on_mount(self):
        self.layout_size = 6

    def render(self):
        name = KaskadeName()

        kafka_info = Table(box=None, expand=False)
        kafka_info.add_column(style="bold blue")
        kafka_info.add_column()

        kafka_info.add_row("kafka:", self.kafka_version)
        kafka_info.add_row("brokers:", str(self.total_brokers))
        kafka_info.add_row("schemas:", "yes" if self.has_schemas else "no")
        kafka_info.add_row(
            "protocol:", self.protocol.lower() if self.protocol else "plain"
        )

        shortcuts = Table(box=None, expand=False)
        shortcuts.add_column(style="magenta bold")
        shortcuts.add_column(style="yellow bold")

        shortcuts.add_row("quit:", Keys.ControlC + "/q")
        shortcuts.add_row("refresh:", Keys.F5)
        shortcuts.add_row("navigate:", "\u2190 \u2192 \u2191 \u2193")

        return Columns([name, kafka_info, shortcuts], padding=3)
