from confluent_kafka import KafkaException
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult, RenderResult
from textual.containers import Container
from textual.keys import Keys
from textual.widget import Widget
from textual.widgets import DataTable

from kaskade.colors import PRIMARY
from kaskade.services import ConsumerService
from kaskade.unicodes import LEFT, RIGHT, UP, DOWN
from kaskade.widgets import KaskadeBanner


class Shortcuts(Widget):

    def render(self) -> RenderResult:
        table = Table(box=None, show_header=False, padding=(0, 1, 0, 0))
        table.add_column(style=f"bold {PRIMARY}")
        table.add_column()

        table.add_row("show", "enter")
        table.add_row("scroll", f"{LEFT} {RIGHT} {UP} {DOWN}")
        table.add_row("more", ">")
        table.add_row("quit", Keys.ControlC)

        return table


class Header(Widget):

    def compose(self) -> ComposeResult:
        yield KaskadeBanner(short=False, include_version=True, include_slogan=True)
        yield Shortcuts()


class Body(Container):
    BINDINGS = [(">", "consume")]

    def __init__(self, topic: str, kafka_conf: dict[str, str]):
        super().__init__()
        self.topic = topic
        self.consumer = ConsumerService(topic, kafka_conf)

    def compose(self) -> ComposeResult:
        yield DataTable()

    def on_unmount(self) -> None:
        self.consumer.close()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.border_subtitle = f"\\[[{PRIMARY}]consumer mode[/]]"
        table.zebra_stripes = True
        table.border_title = self.topic

        table.add_column("message", width=50)
        table.add_column("date", width=10)
        table.add_column("time", width=8)
        table.add_column(Text("partition", justify="right"), width=9)
        table.add_column(Text("offset", justify="right"), width=9)
        table.add_column(Text("headers", justify="right"), width=9)

        self.run_worker(self.action_consume())

    async def action_consume(self) -> None:
        table = self.query_one(DataTable)
        table.loading = True

        try:
            records = await self.consumer.consume()
            for record in records:
                key_and_value = Table(box=None, show_header=False, padding=0)
                key_and_value.add_column(style="bold", width=7)
                key_and_value.add_column(overflow="ellipsis", width=43, no_wrap=True)
                key_and_value.add_row("key:", str(record.key) if record.key else "")
                key_and_value.add_row("value:", str(record.value))
                row = [
                    key_and_value,
                    str(record.date.strftime("%Y-%m-%d")) if record.date else "",
                    str(record.date.strftime("%H:%M:%S")) if record.date else "",
                    Text(str(record.partition), justify="right"),
                    Text(str(record.offset), justify="right"),
                    Text(str(record.headers_count()), justify="right"),
                ]
                table.add_row(*row, height=2)
            table.border_title = f"{self.topic} \\[[{PRIMARY}]{table.row_count}[/]]"
            table.loading = False
            table.focus()
        except Exception as ex:
            if isinstance(ex, KafkaException):
                message = ex.args[0].str()
            else:
                message = str(ex)

            self.notify(message, severity="error", title="kafka error")


class KaskadeConsumer(App):
    CSS_PATH = "styles.css"

    def __init__(self, topic: str, kafka_conf: dict[str, str], schema_conf: dict[str, str]):
        super().__init__()
        self.topic = topic
        self.kafka_conf = kafka_conf

    def on_mount(self) -> None:
        self.use_command_palette = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Body(self.topic, self.kafka_conf)
