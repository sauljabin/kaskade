from typing import Any

from rich.table import Table
from textual.app import App, ComposeResult, RenderResult
from textual.binding import Binding
from textual.containers import Container, ScrollableContainer
from textual.screen import ModalScreen

from textual.widget import Widget
from textual.widgets import DataTable, Pretty, ListView, ListItem, Label

from kaskade.colors import PRIMARY, SECONDARY
from kaskade.models import Record, Format
from kaskade.services import ConsumerService
from kaskade.admin import notify_error, KaskadeBanner

CHUNKS_SHORTCUT = "#"
NEXT_SHORTCUT = ">"
QUIT_SHORTCUT = "ctrl+c"
SUBMIT_SHORTCUT = "enter"
BACK_SHORTCUT = "escape"
FILTER_SHORTCUT = "/"


class Shortcuts(Widget):

    def render(self) -> RenderResult:
        table = Table(box=None, show_header=False, padding=(0, 1, 0, 0))
        table.add_column(style=PRIMARY)
        table.add_column(style=SECONDARY)

        table.add_row("show:", SUBMIT_SHORTCUT)
        table.add_row("more:", NEXT_SHORTCUT)
        table.add_row("filter:", FILTER_SHORTCUT)
        table.add_row("chunk:", CHUNKS_SHORTCUT)
        table.add_row("quit:", QUIT_SHORTCUT)

        return table


class Header(Widget):

    def compose(self) -> ComposeResult:
        yield KaskadeBanner(short=True, include_version=True, include_slogan=False)
        yield Shortcuts()


class ChunkSizeScreen(ModalScreen[int]):
    BINDINGS = [Binding(BACK_SHORTCUT, "close")]

    def __init__(self, current_size: int):
        super().__init__()
        self.current_size = current_size
        self.items = [ListItem(Label(size), name=size) for size in ("25", "50", "100", "500")]

    def _get_index(self, size: int) -> int:
        for i, item in enumerate(self.items):
            if item.name == str(size):
                return i
        return 0

    def compose(self) -> ComposeResult:
        view = ListView(*self.items, initial_index=self._get_index(self.current_size))
        view.border_title = "chunk size"
        view.border_subtitle = f"[{PRIMARY}]change:[/] {SUBMIT_SHORTCUT} [{SECONDARY}]|[/] [{PRIMARY}]back:[/] {BACK_SHORTCUT}"
        yield view

    def action_close(self) -> None:
        self.dismiss()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        chunk_size = int(event.item.name) if event.item.name is not None else self.current_size
        self.dismiss(chunk_size)


class TopicScreen(ModalScreen):

    BINDINGS = [Binding(BACK_SHORTCUT, "close")]

    def __init__(self, topic: str, partition: int, offset: int, data: dict[str, Any]):
        super().__init__()
        self.data = data
        self.topic = topic
        self.partition = partition
        self.record_offset = offset

    def compose(self) -> ComposeResult:
        container = ScrollableContainer()
        container.border_title = f"record \\[[{PRIMARY}]{self.topic}[/]]\\[[{PRIMARY}]{self.partition}[/]]\\[[{PRIMARY}]{self.record_offset}[/]]"
        container.border_subtitle = f"[{PRIMARY}]back:[/] {BACK_SHORTCUT}"
        with container:
            yield Pretty(self.data)

    def action_close(self) -> None:
        self.dismiss()


class ListRecords(Container):
    BINDINGS = [
        Binding(NEXT_SHORTCUT, "consume"),
        Binding(CHUNKS_SHORTCUT, "change_chunk"),
        Binding(SUBMIT_SHORTCUT, "show_message", priority=True),
    ]

    def __init__(self, consumer: ConsumerService):
        super().__init__()
        self.topic = consumer.topic
        self.consumer = consumer
        self.records: dict[str, Record] = {}
        self.current_record: Record | None = None

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

    def action_change_chunk(self) -> None:
        def dismiss(result: int | None) -> None:
            if result is None:
                return
            self.consumer.page_size = result

        self.app.push_screen(ChunkSizeScreen(self.consumer.page_size), dismiss)

    def action_show_message(self) -> None:
        if self.current_record is None:
            return
        try:
            self.app.push_screen(
                TopicScreen(
                    self.current_record.topic,
                    self.current_record.partition,
                    self.current_record.offset,
                    self.current_record.dict(),
                )
            )
        except Exception as ex:
            notify_error(self.app, "deserialization error", ex)

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
                key_and_value.add_row("key:", record.key_str())
                key_and_value.add_row("value:", record.value_str())
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
            notify_error(self.app, "error consuming records", ex)

        table.loading = False
        table.focus()


class KaskadeConsumer(App):
    CSS_PATH = "styles.css"

    def __init__(
        self, topic: str, kafka_conf: dict[str, str], key_format: Format, value_format: Format
    ):
        super().__init__()
        self.topic = topic
        self.kafka_conf = kafka_conf
        self.use_command_palette = False
        self.key_format = key_format
        self.value_format = value_format

    def compose(self) -> ComposeResult:
        yield Header()
        yield ListRecords(
            ConsumerService(
                self.topic,
                self.kafka_conf,
                key_format=self.key_format,
                value_format=self.value_format,
            )
        )
