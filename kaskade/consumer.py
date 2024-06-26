from confluent_kafka import KafkaException
from rich.table import Table
from textual.app import App, ComposeResult, RenderResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import ModalScreen

from textual.widget import Widget
from textual.widgets import DataTable, Pretty

from kaskade import logger
from kaskade.colors import PRIMARY, SECONDARY
from kaskade.models import Record
from kaskade.services import ConsumerService
from kaskade.unicodes import LEFT, RIGHT, UP, DOWN
from kaskade.widgets import KaskadeBanner


NEXT_SHORTCUT = ">"
QUIT_SHORTCUT = "ctrl+c"
SUBMIT_SHORTCUT = "enter"


class Shortcuts(Widget):

    def render(self) -> RenderResult:
        table = Table(box=None, show_header=False, padding=(0, 1, 0, 0))
        table.add_column(style=PRIMARY)
        table.add_column(style=SECONDARY)

        table.add_row("show:", SUBMIT_SHORTCUT)
        table.add_row("scroll:", f"{LEFT} {RIGHT} {UP} {DOWN}")
        table.add_row("more:", NEXT_SHORTCUT)
        table.add_row("quit:", QUIT_SHORTCUT)

        return table


class Header(Widget):

    def compose(self) -> ComposeResult:
        yield KaskadeBanner(short=True, include_version=True, include_slogan=False)
        yield Shortcuts()


class TopicScreen(ModalScreen):

    def __init__(self, record: Record):
        super().__init__()
        self.record = record

    def compose(self) -> ComposeResult:
        pretty = Pretty(self.record.dict())
        pretty.border_title = f"record \\[[{PRIMARY}]{self.record.topic}[/]]\\[[{PRIMARY}]{self.record.partition}[/]]\\[[{PRIMARY}]{self.record.offset}[/]]"
        yield pretty


class ListRecords(Container):
    BINDINGS = [
        Binding(NEXT_SHORTCUT, "consume"),
        Binding(SUBMIT_SHORTCUT, "show_message", priority=True),
    ]

    def __init__(self, topic: str, kafka_conf: dict[str, str]):
        super().__init__()
        self.topic = topic
        self.records: dict[str, Record] = {}
        self.current_record: Record | None = None
        self.consumer = ConsumerService(topic, kafka_conf)

    def compose(self) -> ComposeResult:
        table: DataTable = DataTable()
        table.cursor_type = "row"
        table.border_subtitle = f"\\[[{PRIMARY}]consumer mode[/]]"
        table.zebra_stripes = True
        table.border_title = f"records \\[[{PRIMARY}]{self.topic}[/]]\\[[{PRIMARY}]0[/]]"

        table.add_column("message", width=50)
        table.add_column("datetime", width=10)
        table.add_column("partition", width=9)
        table.add_column("offset", width=9)
        table.add_column("headers", width=9)

        yield table

    def on_unmount(self) -> None:
        self.consumer.close()

    def on_mount(self) -> None:
        self.run_worker(self.action_consume())

    def action_show_message(self) -> None:
        if self.current_record is None:
            return
        self.app.push_screen(TopicScreen(self.current_record))

    def on_data_table_row_highlighted(self, data: DataTable.RowHighlighted) -> None:
        if data.row_key.value is None:
            return
        self.current_record = self.records.get(data.row_key.value)

    async def action_consume(self) -> None:
        table = self.query_one(DataTable)
        table.loading = True

        try:
            records = await self.consumer.consume()
            for record in records:
                self.records[str(record)] = record
                key_and_value = Table(box=None, show_header=False, padding=0)
                key_and_value.add_column(style="bold", width=7)
                key_and_value.add_column(overflow="ellipsis", width=43, no_wrap=True)
                key_and_value.add_row("key:", str(record.key) if record.key else "")
                key_and_value.add_row("value:", str(record.value))
                row = [
                    key_and_value,
                    record.date,
                    str(record.partition),
                    str(record.offset),
                    str(record.headers_count()),
                ]
                table.add_row(*row, height=2, key=str(record))
            table.border_title = (
                f"records \\[[{PRIMARY}]{self.topic}[/]]\\[[{PRIMARY}]{table.row_count}[/]]"
            )
        except Exception as ex:
            self.notify_error(ex)

        table.loading = False
        table.focus()

    def notify_error(self, ex: Exception) -> None:
        if isinstance(ex, KafkaException):
            message = ex.args[0].str()
        else:
            message = str(ex)
        logger.exception(ex)
        self.notify(message, severity="error", title="kafka error")


class KaskadeConsumer(App):
    CSS_PATH = "styles.css"

    def __init__(self, topic: str, kafka_conf: dict[str, str], schema_conf: dict[str, str]):
        super().__init__()
        self.topic = topic
        self.kafka_conf = kafka_conf
        self.use_command_palette = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield ListRecords(self.topic, self.kafka_conf)
