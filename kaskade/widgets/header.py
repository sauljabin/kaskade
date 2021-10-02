from rich.columns import Columns
from rich.table import Table
from textual.keys import Keys

from kaskade.kaskade import KASKADE
from kaskade.tui_widget import TuiWidget


class Header(TuiWidget):
    name = "Header"
    kafka_version = "unknown"
    total_brokers = 0
    protocol = "unknown"
    has_schemas = False

    def __init__(self):
        super().__init__(name=self.name)
        self.layout_size = 6

    def render(self):
        name = KASKADE.riched_name()

        kafka_info = Table(box=None, expand=False)
        kafka_info.add_column(style="bold blue")
        kafka_info.add_column()

        kafka_info.add_row(
            "protocol:", self.protocol.lower() if self.protocol else "plain"
        )
        kafka_info.add_row("brokers:", str(self.total_brokers))
        kafka_info.add_row("schemas:", "yes" if self.has_schemas else "no")
        kafka_info.add_row("kafka:", self.kafka_version)

        shortcuts = Table(box=None, expand=False)
        shortcuts.add_column(style="magenta bold")
        shortcuts.add_column(style="yellow bold")

        shortcuts.add_row("navigate:", "\u2190 \u2192 \u2191 \u2193")
        shortcuts.add_row("refresh:", Keys.F5)
        shortcuts.add_row("quit:", Keys.ControlC + "/q")

        return Columns([name, kafka_info, shortcuts], padding=5)
