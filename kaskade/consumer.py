from typing import Any

from rich.style import Style
from rich.table import Table
from rich.theme import Theme
from textual import work
from textual.app import App, ComposeResult, RenderResult
from textual.binding import Binding
from textual.containers import Container, ScrollableContainer
from textual.screen import ModalScreen

from textual.widget import Widget
from textual.widgets import DataTable, Pretty, ListView, ListItem, Label, Input

from kaskade.colors import PRIMARY, SECONDARY
from kaskade.models import Record
from kaskade.deserializers import Format, DeserializerPool
from kaskade.services import ConsumerService
from kaskade.utils import notify_error
from kaskade.banner import KaskadeBanner

CHUNKS_SHORTCUT = "#"
NEXT_SHORTCUT = ">"
QUIT_SHORTCUT = "ctrl+c"
SUBMIT_SHORTCUT = "enter"
BACK_SHORTCUT = "escape"
FILTER_SHORTCUT = "/"


class ConsumerShortcuts(Widget):

    SHORTCUTS = [
        ["all:", BACK_SHORTCUT, "show:", SUBMIT_SHORTCUT],
        ["more:", NEXT_SHORTCUT, "filter:", FILTER_SHORTCUT],
        ["quit:", QUIT_SHORTCUT, "chunk:", CHUNKS_SHORTCUT],
    ]

    def render(self) -> RenderResult:
        table = Table(box=None, show_header=False, padding=(0, 0, 0, 1))
        table.add_column(style=PRIMARY)
        table.add_column(style=SECONDARY)
        table.add_column(style=PRIMARY)
        table.add_column(style=SECONDARY)

        for shortcuts in self.SHORTCUTS:
            table.add_row(*shortcuts)

        return table


class Header(Widget):

    def compose(self) -> ComposeResult:
        yield ConsumerShortcuts()
        yield KaskadeBanner(include_version=True, include_slogan=False)


class FilterRecordScreen(ModalScreen[tuple[str, str, str, str]]):
    BINDINGS = [Binding(BACK_SHORTCUT, "back")]

    def __init__(self) -> None:
        super().__init__()
        self.key_filter = ""
        self.value_filter = ""
        self.partition_filter = ""
        self.header_filter = ""

    def compose(self) -> ComposeResult:
        input_key = Input(id="key", placeholder="word to match with keys")
        input_key.border_title = "key"

        input_value = Input(id="value", placeholder="word to match with values")
        input_value.border_title = "value"

        input_partition = Input(id="partition", placeholder="partition number", type="integer")
        input_partition.border_title = "partition"

        input_header = Input(id="header", placeholder="word to match with header values")
        input_header.border_title = "header"

        container = Container()
        container.border_title = "filter records"
        container.border_subtitle = f"[{PRIMARY}]filter:[/] {SUBMIT_SHORTCUT} [{SECONDARY}]|[/] [{PRIMARY}]back:[/] {BACK_SHORTCUT}"

        with container:
            yield input_key
            yield input_value
            yield input_partition
            yield input_header

    def on_input_submitted(self) -> None:
        input_key = self.query_one("#key", Input)
        self.key_filter = input_key.value

        input_value = self.query_one("#value", Input)
        self.value_filter = input_value.value

        input_partition = self.query_one("#partition", Input)
        self.partition_filter = input_partition.value

        input_header = self.query_one("#header", Input)
        self.header_filter = input_header.value

        self.dismiss(
            (self.key_filter, self.value_filter, self.partition_filter, self.header_filter)
        )

    def action_back(self) -> None:
        self.dismiss()


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
        Binding(FILTER_SHORTCUT, "filter"),
        Binding(SUBMIT_SHORTCUT, "show_message", priority=True),
        Binding(BACK_SHORTCUT, "all"),
    ]

    def __init__(
        self,
        topic: str,
        kafka_config: dict[str, str],
        schema_registry_config: dict[str, str],
        protobuf_config: dict[str, str],
        key_format: Format,
        value_format: Format,
    ):
        super().__init__()
        self.topic = topic
        self.kafka_config = kafka_config
        self.deserializer_factory = DeserializerPool(schema_registry_config, protobuf_config)
        self.key_format = key_format
        self.value_format = value_format
        self.consumer = self._new_consumer()
        self.records: dict[str, Record] = {}
        self.current_record: Record | None = None
        self.key_filter = ""
        self.value_filter = ""
        self.partition_filter = ""
        self.header_filter = ""

    def _new_consumer(self) -> ConsumerService:
        return ConsumerService(
            self.topic,
            self.kafka_config,
            self.deserializer_factory,
            self.key_format,
            self.value_format,
        )

    def _get_title(self) -> str:
        def style(text: str) -> str:
            return f"\\[[{PRIMARY}]{text}[/]]"

        title_filter = ""

        if self.key_filter:
            title_filter += style(f"k:*{self.key_filter}*")

        if self.value_filter:
            title_filter += style(f"v:*{self.value_filter}*")

        if self.partition_filter:
            title_filter += style(f"p:{self.partition_filter}")

        if self.header_filter:
            title_filter += style(f"h:*{self.header_filter}*")

        return f"records \\[[{PRIMARY}]{self.topic}[/]]{title_filter}\\[[{PRIMARY}]{len(self.records)}[/]]"

    def compose(self) -> ComposeResult:
        table: DataTable = DataTable()
        table.cursor_type = "row"
        table.border_subtitle = f"\\[[{PRIMARY}]consumer mode[/]]"
        table.zebra_stripes = True
        table.border_title = self._get_title()

        table.add_column("message", width=50)
        table.add_column("datetime", width=10)
        table.add_column("partition", width=9)
        table.add_column("offset", width=9)
        table.add_column("headers", width=9)

        yield table

    def on_unmount(self) -> None:
        self.consumer.close()

    def on_mount(self) -> None:
        self.action_consume()

    def action_all(self) -> None:
        self.key_filter, self.value_filter, self.partition_filter, self.header_filter = (
            "",
            "",
            "",
            "",
        )
        self._filter()

    def action_filter(self) -> None:
        def dismiss(result: tuple[str, str, str, str] | None) -> None:
            if result is None:
                return
            self.key_filter, self.value_filter, self.partition_filter, self.header_filter = result
            self._filter()

        self.app.push_screen(FilterRecordScreen(), dismiss)

    def _filter(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        self.consumer = self._new_consumer()
        self.records = {}
        table.border_title = self._get_title()
        self.action_consume()

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

    @work
    async def action_consume(self) -> None:
        table = self.query_one(DataTable)
        table.loading = True

        try:
            records = await self.consumer.consume(
                partition_filter=int(self.partition_filter) if self.partition_filter else None,
                key_filter=self.key_filter if self.key_filter else None,
                value_filter=self.value_filter if self.value_filter else None,
                header_filter=self.header_filter if self.header_filter else None,
            )

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
            table.border_title = self._get_title()
        except Exception as ex:
            notify_error(self.app, "error consuming records", ex)

        table.loading = False
        table.focus()


class KaskadeConsumer(App):
    CSS_PATH = "styles.css"

    def __init__(
        self,
        topic: str,
        kafka_config: dict[str, str],
        schema_registry_config: dict[str, str],
        protobuf_config: dict[str, str],
        key_format: Format,
        value_format: Format,
    ):
        super().__init__()
        self.use_command_palette = False
        self.topic = topic
        self.kafka_config = kafka_config
        self.schema_registry_config = schema_registry_config
        self.protobuf_config = protobuf_config
        self.key_format = key_format
        self.value_format = value_format

    def on_mount(self) -> None:
        self.console.push_theme(Theme({"repr.str": Style(color=PRIMARY)}))

    def compose(self) -> ComposeResult:
        yield Header()
        yield ListRecords(
            self.topic,
            self.kafka_config,
            self.schema_registry_config,
            self.protobuf_config,
            self.key_format,
            self.value_format,
        )
