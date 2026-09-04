from collections.abc import Callable
from inspect import isawaitable
from typing import Any, ClassVar

from confluent_kafka import KafkaException
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Grid
from textual.content import Content
from textual.coordinate import Coordinate
from textual.widgets import (
    DataTable,
    Footer,
    Input,
    OptionList,
    Static,
    TabbedContent,
    TabPane,
)
from textual.widgets.option_list import Option

from kaskade.colors import NULL, PRIMARY
from kaskade.colors import WARNING as WARNING_STYLE
from kaskade.commands import RecordFilters
from kaskade.deserializers import (
    DESERIALIZATION_EXCEPTIONS,
    Deserialization,
    DeserializerPool,
)
from kaskade.help import HelpableModalScreen, modal_bindings
from kaskade.models import DeserializationOutcome, PartitionSelection, Record
from kaskade.record_export import (
    deliver_record,
    readable_json,
    record_json,
    record_json_renderable,
)
from kaskade.services import ConsumerService
from kaskade.themes import KaskadeApp
from kaskade.unicodes import WARNING as WARNING_INDICATOR
from kaskade.utils import copy_text, notify_error
from kaskade.widgets import (
    KaskadeHeader,
    KaskadeOptionList,
    KaskadeScrollableContainer,
    StretchyDataTable,
    TableFrame,
    labelled_value,
)

CHUNKS_SHORTCUT = "#"
NEXT_SHORTCUT = "n"
PREVIOUS_SHORTCUT = "N,p"
SUBMIT_SHORTCUT = "enter"
BACK_SHORTCUT = "escape"
FILTER_SHORTCUT = "/,ctrl+f"
EXPORT_SHORTCUT = "ctrl+e"
COPY_RECORD_SHORTCUT = "y"
CONSUMER_EXCEPTIONS: tuple[type[Exception], ...] = (KafkaException,)
KEY_COLUMN_INDEX = 0
VALUE_COLUMN_INDEX = 1
KILOBYTE = 1_000
MEGABYTE = 1_000_000


def format_payload_size(size: int | None) -> str:
    if size is None:
        return "—"
    if size >= MEGABYTE:
        return f"{size / MEGABYTE:.2f} MB"
    kilobytes = size / KILOBYTE
    precision = 3 if 0 < kilobytes < 0.01 else 2
    return f"{kilobytes:.{precision}f} KB"


def record_payload_size(record: Record) -> int:
    size = sum(len(payload) for payload in (record.key, record.value) if payload is not None)
    return size + sum(
        len(header.key.encode("utf-8")) + (len(header.value) if header.value is not None else 0)
        for header in record.headers
    )


class RecordDataTable(StretchyDataTable[str | Text]):
    """A records table with diagnostic tooltips for individual cells."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("cursor_foreground_priority", "renderable")
        super().__init__(**kwargs)
        self._cell_tooltips: dict[Coordinate, Text] = {}

    def set_cell_tooltip(self, coordinate: Coordinate, tooltip: Text) -> None:
        self._cell_tooltips[coordinate] = tooltip

    def clear_cell_tooltips(self) -> None:
        self._cell_tooltips.clear()
        self.tooltip = None

    def watch_hover_coordinate(self, old: Coordinate, value: Coordinate) -> None:
        super().watch_hover_coordinate(old, value)
        self.tooltip = self._cell_tooltips.get(value)


class FilterRecordScreen(HelpableModalScreen[RecordFilters]):
    BINDING_GROUP_TITLE = "Filter Records"
    AUTO_FOCUS = "#key"
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            SUBMIT_SHORTCUT,
            "apply_filters",
            "Apply Filters",
            priority=True,
            tooltip="Apply the record filters.",
            id="kaskade.filter-records.apply",
        ),
        Binding(
            BACK_SHORTCUT,
            "back",
            "Back",
            tooltip="Close the filter without applying it.",
            id="kaskade.filter-records.close",
        ),
    )

    def __init__(self) -> None:
        super().__init__()

    def compose(self) -> ComposeResult:
        input_key = Input(id="key", placeholder="Key contains…", classes="kaskade-input")
        input_key.border_title = "Key"

        input_value = Input(id="value", placeholder="Value contains…", classes="kaskade-input")
        input_value.border_title = "Value"

        input_partition = Input(
            id="partition",
            placeholder="Partition number",
            type="integer",
            classes="kaskade-input",
        )
        input_partition.border_title = "Partition"

        input_header = Input(
            id="header", placeholder="Header value contains…", classes="kaskade-input"
        )
        input_header.border_title = "Header"

        container = Container(classes="record-filter")
        container.border_title = f"[{PRIMARY}]Filter Records[/]"

        with container:
            yield input_key
            yield input_value
            yield input_partition
            yield input_header
        yield Footer(compact=True)

    def on_input_submitted(self) -> None:
        self.action_apply_filters()

    def action_apply_filters(self) -> None:
        partition_value = self.query_one("#partition", Input).value
        self.dismiss(
            RecordFilters(
                key=self.query_one("#key", Input).value,
                value=self.query_one("#value", Input).value,
                partition=int(partition_value) if partition_value else None,
                header=self.query_one("#header", Input).value,
            )
        )

    def action_back(self) -> None:
        self.dismiss()


class ChunkSizeScreen(HelpableModalScreen[int]):
    BINDING_GROUP_TITLE = "Chunk Size"
    AUTO_FOCUS = "#chunk-size"
    CHUNK_SIZES = ("25", "50", "100", "500", "1000", "1500")
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            SUBMIT_SHORTCUT,
            "select",
            "Select",
            priority=True,
            tooltip="Use the highlighted chunk size.",
            id="kaskade.chunk-size.select",
        ),
        Binding(
            BACK_SHORTCUT,
            "close",
            "Back",
            tooltip="Keep the current chunk size.",
            id="kaskade.chunk-size.close",
        ),
    )

    def __init__(self, current_size: int):
        super().__init__()
        self.current_size = current_size

    def _get_index(self, size: int) -> int:
        try:
            return self.CHUNK_SIZES.index(str(size))
        except ValueError:
            return 0

    def compose(self) -> ComposeResult:
        view = KaskadeOptionList(
            *(Option(size, id=size) for size in self.CHUNK_SIZES),
            id="chunk-size",
            compact=True,
        )
        view.highlighted = self._get_index(self.current_size)
        view.border_title = f"[{PRIMARY}]Chunk Size[/]"
        yield view
        yield Footer(compact=True)

    def action_close(self) -> None:
        self.dismiss()

    def action_select(self) -> None:
        self.query_one(KaskadeOptionList).action_select()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        chunk_size = int(event.option_id) if event.option_id is not None else self.current_size
        self.dismiss(chunk_size)


class RecordFieldDetails(Container):
    """Present one deserialized field with diagnostics and content."""

    def __init__(
        self,
        outcome: DeserializationOutcome,
        *,
        payload_size: int | None,
        field_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.outcome = outcome
        self.payload_size = payload_size
        self.field_name = field_name

    def _deserializer(self) -> str:
        parts = [self.outcome.requested.name]
        if self.outcome.schema is not None:
            parts.append(self.outcome.schema.type)
        if (
            not self.outcome.used_fallback
            and self.outcome.requested == Deserialization.BYTES
            and isinstance(self.outcome.content, bytes)
        ):
            parts.append(self.outcome.bytes_encoding.name)
        return " · ".join(parts)

    def _schema(self) -> str:
        if self.outcome.schema is None:
            return "—"
        schema = self.outcome.schema.dict()
        provider = str(schema["provider"]).title()
        identity = schema.get("subject")
        if identity is None:
            identity = "/".join(
                str(part) for part in (schema.get("group"), schema.get("artifact")) if part
            )
        parts = [provider, f"ID {schema['id']}"]
        if identity:
            parts.append(str(identity))
        if schema.get("version") is not None:
            parts[-1] = f"{parts[-1]} v{schema['version']}"
        return " · ".join(parts)

    def _error(self) -> Text:
        error = Text("ERROR", style="bold error")
        if self.outcome.error is not None:
            error.append(f"\n{self.outcome.error}")
            error.append("\nFallback: ", style="secondary")
            error.append(
                f"{Deserialization.BYTES.name} · {self.outcome.bytes_encoding.name}",
                style=WARNING_STYLE,
            )
        return error

    def compose(self) -> ComposeResult:
        field_name = Static(classes="record-field-name")
        field_name.display = self.field_name is not None
        if self.field_name is not None:
            field_name.update(labelled_value("Header", self.field_name))
        yield field_name

        with Grid(classes="record-diagnostics"):
            yield Static(
                labelled_value("Deserializer", self._deserializer()),
                classes="record-diagnostic record-deserializer",
            )
            yield Static(
                labelled_value("Schema", self._schema()),
                classes="record-diagnostic record-schema",
            )
            yield Static(
                labelled_value("Size", format_payload_size(self.payload_size)),
                classes="record-diagnostic record-size",
            )

        error = Static(self._error(), classes="record-error")
        error.display = self.outcome.error is not None
        yield error
        yield Static(
            Text(
                ("FALLBACK CONTENT" if self.outcome.error is not None else "CONTENT"),
                style="muted",
            ),
            classes="record-content-label",
        )
        yield Static(
            record_json_renderable(self.outcome.dict()["content"]),
            classes="record-content",
        )

    def update_outcome(
        self,
        outcome: DeserializationOutcome,
        *,
        payload_size: int | None,
        field_name: str | None = None,
    ) -> None:
        self.outcome = outcome
        self.payload_size = payload_size
        self.field_name = field_name
        name = self.query_one(".record-field-name", Static)
        name.display = field_name is not None
        if field_name is not None:
            name.update(labelled_value("Header", field_name))
        self.query_one(".record-deserializer", Static).update(
            labelled_value("Deserializer", self._deserializer())
        )
        self.query_one(".record-schema", Static).update(labelled_value("Schema", self._schema()))
        self.query_one(".record-size", Static).update(
            labelled_value("Size", format_payload_size(self.payload_size))
        )
        error = self.query_one(".record-error", Static)
        error.display = outcome.error is not None
        error.update(self._error())
        self.query_one(".record-content-label", Static).update(
            Text(
                "FALLBACK CONTENT" if outcome.error is not None else "CONTENT",
                style="muted",
            )
        )
        self.query_one(".record-content", Static).update(
            record_json_renderable(outcome.dict()["content"])
        )


class TopicScreen(HelpableModalScreen[Record]):
    BINDING_GROUP_TITLE = "Record Details"
    AUTO_FOCUS = "Tabs"
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            COPY_RECORD_SHORTCUT,
            "copy_record",
            "Copy Record",
            show=False,
            tooltip="Copy the active record detail as JSON to the clipboard.",
            id="kaskade.records.copy",
        ),
        Binding(
            EXPORT_SHORTCUT,
            "export_record",
            "Export Record",
            show=False,
            tooltip="Export the record as a JSON file.",
            id="kaskade.records.export",
        ),
        Binding(
            PREVIOUS_SHORTCUT,
            "previous_record",
            "Previous Record",
            show=False,
            tooltip="Show the previous consumed record.",
            id="kaskade.record-details.previous",
        ),
        Binding(
            NEXT_SHORTCUT,
            "next_record",
            "Next Record",
            show=False,
            tooltip="Show the next consumed record.",
            id="kaskade.record-details.next",
        ),
        Binding(
            BACK_SHORTCUT,
            "close",
            "Back",
            tooltip="Close the record details.",
            id="kaskade.record-details.close",
        ),
    )

    def __init__(
        self,
        record: Record,
        records: tuple[Record, ...] = (),
        on_record_changed: Callable[[Record], None] | None = None,
    ):
        super().__init__()
        self.records = records or (record,)
        record_index = next(
            (index for index, candidate in enumerate(self.records) if candidate is record),
            None,
        )
        if record_index is None:
            self.records = (record, *self.records)
            record_index = 0
        self.record_index = record_index
        self.record = record
        self.data = record.dict()
        self.on_record_changed = on_record_changed

    def _title(self) -> str:
        return (
            rf"[{PRIMARY}]Record Details[/] "
            rf"\[[{PRIMARY}]{self.record.topic}[/]]"
            rf"\[[{PRIMARY}]{self.record.partition}[/]]"
            rf"\[[{PRIMARY}]{self.record.offset}[/]]"
        )

    def _metadata(self) -> tuple[tuple[str, str, str], ...]:
        return (
            (
                "record-total-size",
                "Total Size",
                format_payload_size(record_payload_size(self.record)),
            ),
            ("record-partition", "Partition", str(self.record.partition)),
            ("record-offset", "Offset", str(self.record.offset)),
            (
                "record-timestamp",
                "Timestamp",
                self.record.timestamp_str() or "null",
            ),
        )

    @staticmethod
    def _metadata_content(label: str, value: str) -> Text:
        return labelled_value(label, value)

    def _headers_list(self) -> KaskadeOptionList:
        headers = KaskadeOptionList(
            *(
                Option(header.key, id=str(index))
                for index, header in enumerate(self.record.headers)
            ),
            id="record-headers-list",
            compact=True,
        )
        headers.highlighted = 0 if self.record.headers else None
        return headers

    def compose(self) -> ComposeResult:
        container = Container(classes="record-details")
        container.border_title = self._title()
        with container:
            with Grid(id="record-metadata"):
                for metadata_id, label, value in self._metadata():
                    yield Static(
                        self._metadata_content(label, value),
                        id=metadata_id,
                        classes="record-metadata-cell",
                    )
            with TabbedContent(initial="key", id="record-details-tabs"):
                with (
                    TabPane("Key", id="key"),
                    KaskadeScrollableContainer(classes="record-detail-scroll"),
                ):
                    yield RecordFieldDetails(
                        self.record.key_outcome(),
                        payload_size=(
                            len(self.record.key) if self.record.key is not None else None
                        ),
                        id="record-key-details",
                    )
                with (
                    TabPane("Value", id="value"),
                    KaskadeScrollableContainer(classes="record-detail-scroll"),
                ):
                    yield RecordFieldDetails(
                        self.record.value_outcome(),
                        payload_size=(
                            len(self.record.value) if self.record.value is not None else None
                        ),
                        id="record-value-details",
                    )
                with (
                    TabPane(
                        Content(f"Headers [{self.record.headers_count()}]"),
                        id="headers",
                    ),
                    Container(classes="record-headers-layout"),
                ):
                    headers = self._headers_list()
                    headers.display = bool(self.record.headers)
                    yield headers
                    empty = Static("No headers", id="record-headers-empty")
                    empty.display = not self.record.headers
                    yield empty
                    header_scroll = KaskadeScrollableContainer(
                        classes="record-detail-scroll record-header-scroll"
                    )
                    header_scroll.display = bool(self.record.headers)
                    with header_scroll:
                        header = self.record.headers[0] if self.record.headers else None
                        yield RecordFieldDetails(
                            (
                                header.value_outcome()
                                if header is not None
                                else DeserializationOutcome(Deserialization.STRING, None)
                            ),
                            payload_size=(
                                len(header.value)
                                if header is not None and header.value is not None
                                else None
                            ),
                            field_name=header.key if header is not None else None,
                            id="record-header-details",
                        )
                with (
                    TabPane("JSON", id="json"),
                    KaskadeScrollableContainer(classes="record-detail-scroll"),
                ):
                    yield Static(record_json_renderable(self.data), classes="record-json")
        yield Footer(compact=True)

    def action_close(self) -> None:
        self.dismiss(self.record)

    def _show_record(self, index: int) -> None:
        if not 0 <= index < len(self.records):
            return

        record = self.records[index]
        try:
            data = record.dict()
        except DESERIALIZATION_EXCEPTIONS as ex:
            notify_error(self.app, "Deserialization Error", ex)
            return

        self.record_index = index
        self.record = record
        self.data = data
        details = self.query_one(".record-details", Container)
        details.border_title = self._title()
        for metadata_id, label, value in self._metadata():
            self.query_one(f"#{metadata_id}", Static).update(self._metadata_content(label, value))
        tabs = self.query_one(TabbedContent)
        headers_tab = tabs.get_tab("headers")
        assert headers_tab is not None
        headers_tab.label = Content(f"Headers [{record.headers_count()}]")
        self.query_one("#record-key-details", RecordFieldDetails).update_outcome(
            record.key_outcome(),
            payload_size=len(record.key) if record.key is not None else None,
        )
        self.query_one("#record-value-details", RecordFieldDetails).update_outcome(
            record.value_outcome(),
            payload_size=len(record.value) if record.value is not None else None,
        )
        self.query_one(".record-json", Static).update(record_json_renderable(data))
        self._refresh_headers()
        for scroll in self.query(".record-detail-scroll").results(KaskadeScrollableContainer):
            scroll.scroll_home(animate=False)
        self.refresh_bindings()
        if self.on_record_changed is not None:
            self.on_record_changed(record)

    def _refresh_headers(self) -> None:
        headers = self.query_one("#record-headers-list", KaskadeOptionList)
        empty = self.query_one("#record-headers-empty", Static)
        details = self.query_one(".record-header-scroll", KaskadeScrollableContainer)
        headers.clear_options()
        has_headers = bool(self.record.headers)
        headers.display = has_headers
        empty.display = not has_headers
        details.display = has_headers
        if has_headers:
            headers.add_options(
                Option(header.key, id=str(index))
                for index, header in enumerate(self.record.headers)
            )
            headers.highlighted = 0
            header = self.record.headers[0]
            self.query_one("#record-header-details", RecordFieldDetails).update_outcome(
                header.value_outcome(),
                payload_size=len(header.value) if header.value is not None else None,
                field_name=header.key,
            )

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id != "record-headers-list" or event.option_id is None:
            return
        header = self.record.headers[int(event.option_id)]
        self.query_one("#record-header-details", RecordFieldDetails).update_outcome(
            header.value_outcome(),
            payload_size=len(header.value) if header.value is not None else None,
            field_name=header.key,
        )
        self.query_one(".record-header-scroll", KaskadeScrollableContainer).scroll_home(
            animate=False
        )

    def action_previous_record(self) -> None:
        self._show_record(self.record_index - 1)

    def action_next_record(self) -> None:
        self._show_record(self.record_index + 1)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "previous_record":
            return self.record_index > 0
        if action == "next_record":
            return self.record_index < len(self.records) - 1
        return True

    def action_export_record(self) -> None:
        try:
            deliver_record(self.app, self.record)
        except DESERIALIZATION_EXCEPTIONS as ex:
            notify_error(self.app, "Deserialization Error", ex)

    def action_copy_record(self) -> None:
        try:
            active = self.query_one(TabbedContent).active
            if active in {"headers", "key", "value"}:
                copy_text(self.app, readable_json(self.data[active]), f"record {active}")
            else:
                copy_text(self.app, readable_json(self.data), "record JSON")
        except DESERIALIZATION_EXCEPTIONS as ex:
            notify_error(self.app, "Deserialization Error", ex)


class ListRecords(Container):
    BINDING_GROUP_TITLE = "Records"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            SUBMIT_SHORTCUT,
            "show_message",
            "Show Record",
            priority=True,
            tooltip="Open the complete selected record.",
            id="kaskade.records.show",
        ),
        Binding(
            COPY_RECORD_SHORTCUT,
            "copy_record",
            "Copy Record",
            show=False,
            tooltip="Copy the selected record as JSON to the clipboard.",
            id="kaskade.records.copy",
        ),
        Binding(
            EXPORT_SHORTCUT,
            "export_record",
            "Export Record",
            show=False,
            tooltip="Export the selected record as a JSON file.",
            id="kaskade.records.export",
        ),
        Binding(
            NEXT_SHORTCUT,
            "consume",
            "Consume More",
            tooltip="Consume the next chunk of Kafka records.",
            id="kaskade.records.consume",
        ),
        Binding(
            FILTER_SHORTCUT,
            "filter",
            "Filter",
            key_display="/",
            tooltip="Filter records by key, value, partition, or header.",
            id="kaskade.records.filter",
        ),
        Binding(
            CHUNKS_SHORTCUT,
            "change_chunk",
            "Chunk Size",
            tooltip="Change the number of records consumed at a time.",
            id="kaskade.records.chunk-size",
        ),
        Binding(
            BACK_SHORTCUT,
            "all",
            "Show All",
            show=False,
            tooltip="Clear all active record filters.",
            id="kaskade.records.show-all",
        ),
    ]

    def __init__(
        self,
        topic: str,
        kafka_config: dict[str, Any],
        deserializer_factory: DeserializerPool,
        key_deserialization: Deserialization,
        value_deserialization: Deserialization,
        *,
        bytes_config: dict[str, str] | None = None,
        fallback_config: dict[str, str] | None = None,
        partitions: tuple[PartitionSelection, ...] = (),
        consumer: ConsumerService | None = None,
    ):
        super().__init__()
        self.topic = topic
        self.kafka_config = kafka_config
        self.deserializer_factory = deserializer_factory
        self.key_deserialization = key_deserialization
        self.value_deserialization = value_deserialization
        self.bytes_config = bytes_config or {}
        self.fallback_config = fallback_config or {}
        self.partitions = partitions
        self.consumer = consumer or self._new_consumer()
        self.records: dict[str, Record] = {}
        self.current_record: Record | None = None
        self.filters = RecordFilters()
        self._is_consuming = False

    def _new_consumer(self) -> ConsumerService:
        return ConsumerService(
            self.topic,
            self.kafka_config,
            self.deserializer_factory,
            self.key_deserialization,
            self.value_deserialization,
            bytes_config=self.bytes_config,
            fallback_config=self.fallback_config,
            partitions=self.partitions,
        )

    def _get_title(self) -> str:
        def style(text: str) -> str:
            return rf"\[[{PRIMARY}]{text}[/]]"

        title_filter = ""

        if self.filters.key:
            title_filter += style(f"k:*{self.filters.key}*")

        if self.filters.value:
            title_filter += style(f"v:*{self.filters.value}*")

        if self.filters.partition is not None:
            title_filter += style(f"p:{self.filters.partition}")

        if self.filters.header:
            title_filter += style(f"h:*{self.filters.header}*")

        return rf"[{PRIMARY}]Records[/] \[[{PRIMARY}]{self.topic}[/]]{title_filter}\[[{PRIMARY}]{len(self.records)}[/]]"

    def compose(self) -> ComposeResult:
        table = RecordDataTable(id="records-table", classes="main-table")
        table.cursor_type = "row"

        table.add_column("Key", stretch=2)
        table.add_column("Value", stretch=3)
        table.add_column("Size", width=10)
        table.add_column("Timestamp", width=23)
        table.add_column("Partition", width=9)
        table.add_column("Offset", width=6)
        table.add_column("Headers", width=7)

        frame = TableFrame(table, id="records-frame", classes="kaskade-table")
        frame.border_title = self._get_title()
        frame.border_subtitle = rf"\[[{PRIMARY}]Consumer Mode[/]]"
        yield frame

    async def on_unmount(self) -> None:
        result = self.consumer.aclose()
        if isawaitable(result):
            await result

    def on_mount(self) -> None:
        self.query_one("#records-table", DataTable).focus()
        self.action_consume()

    def action_all(self) -> None:
        self.filters = RecordFilters()
        self._filter()

    def action_filter(self) -> None:
        def dismiss(result: RecordFilters | None) -> None:
            if result is None:
                return
            self.filters = result
            self._filter()

        self.app.push_screen(FilterRecordScreen(), dismiss)

    def _filter(self) -> None:
        table = self.query_one(RecordDataTable)
        table.clear_cell_tooltips()
        table.clear()
        self.consumer.close()
        self.consumer = self._new_consumer()
        self.records = {}
        self.current_record = None
        self.refresh_bindings()
        self._update_table_title()
        self.action_consume()

    def _update_table_title(self) -> None:
        self.query_one("#records-frame", TableFrame).border_title = self._get_title()

    def action_change_chunk(self) -> None:
        def dismiss(result: int | None) -> None:
            if result is None:
                return
            self.consumer.page_size = result

        self.app.push_screen(ChunkSizeScreen(self.consumer.page_size), dismiss)

    def action_show_message(self) -> None:
        if self.current_record is None:
            return

        def select_record(record: Record | None) -> None:
            if record is None:
                return
            record_id = str(record)
            try:
                row = tuple(self.records).index(record_id)
            except ValueError:
                return
            table = self.query_one(RecordDataTable)
            table.move_cursor(row=row)
            # DataTable normally repaints only the old and new row. When a modal
            # covers the middle of the table, Textual can leave an exposed segment
            # of the old row highlighted, so invalidate the complete table.
            table.refresh()

        try:
            self.app.push_screen(
                TopicScreen(
                    self.current_record,
                    tuple(self.records.values()),
                    on_record_changed=select_record,
                ),
                select_record,
            )
        except DESERIALIZATION_EXCEPTIONS as ex:
            notify_error(self.app, "Deserialization Error", ex)

    def action_export_record(self) -> None:
        if self.current_record is None:
            return
        try:
            deliver_record(self.app, self.current_record)
        except DESERIALIZATION_EXCEPTIONS as ex:
            notify_error(self.app, "Deserialization Error", ex)

    def action_copy_record(self) -> None:
        if self.current_record is None:
            return
        try:
            copy_text(
                self.app,
                record_json(self.current_record).removesuffix("\n"),
                "record JSON",
            )
        except DESERIALIZATION_EXCEPTIONS as ex:
            notify_error(self.app, "Deserialization Error", ex)

    def on_data_table_row_highlighted(self, data: DataTable.RowHighlighted) -> None:
        if data.row_key is None or data.row_key.value is None:
            return
        self.current_record = self.records.get(data.row_key.value)
        self.refresh_bindings()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Disable contextual actions when their required state is unavailable."""
        if action in {"copy_record", "export_record", "show_message"}:
            return self.current_record is not None
        if action == "all":
            return not self._is_consuming and self.filters.active
        if action in {"change_chunk", "consume", "filter"}:
            return not self._is_consuming
        return True

    def action_consume(self) -> None:
        """Start consuming unless a request is already running."""
        if self._is_consuming:
            return
        self._is_consuming = True
        self.refresh_bindings()
        self.query_one(DataTable).loading = True
        self.consume_records()

    @staticmethod
    def _content_cell(outcome: DeserializationOutcome) -> str | Text:
        if outcome.content is None:
            return Text("null", style=NULL)
        content = outcome.content_str().strip()
        if outcome.used_fallback:
            return Text(
                f"{WARNING_INDICATOR} {content}",
                style=WARNING_STYLE,
            )
        return content

    @classmethod
    def _record_row(cls, record: Record) -> list[str | Text]:
        record.resolve_deserializations()
        return [
            cls._content_cell(record.key_outcome()),
            cls._content_cell(record.value_outcome()),
            format_payload_size(record_payload_size(record)),
            record.timestamp_str(),
            str(record.partition),
            str(record.offset),
            str(record.headers_count()),
        ]

    @staticmethod
    def _warning_tooltip(
        record: Record,
        field_name: str,
        outcome: DeserializationOutcome,
    ) -> Text:
        tooltip = Text()
        tooltip.append(
            f"{WARNING_INDICATOR} {field_name.title()} Deserialization Warning",
            style=WARNING_STYLE,
        )
        tooltip.append(f"\nRecord: {record.topic}[{record.partition}][{record.offset}]")
        tooltip.append(f"\nRequested: {outcome.requested.name}")
        tooltip.append(f"\nFallback: {Deserialization.BYTES.name}")
        tooltip.append(f"\nEncoding: {outcome.bytes_encoding.name}")
        tooltip.append(f"\nError: {outcome.error}")
        return tooltip

    @staticmethod
    def _null_tooltip(record: Record, field_name: str) -> Text:
        tooltip = Text()
        tooltip.append(f"Null {field_name.title()}", style=WARNING_STYLE)
        tooltip.append(f"\nRecord: {record.topic}[{record.partition}][{record.offset}]")
        if field_name == "key":
            tooltip.append("\nThis Kafka record has no key")
        else:
            tooltip.append("\nThis Kafka record is a tombstone")
        return tooltip

    @classmethod
    def _add_cell_tooltips(
        cls,
        table: RecordDataTable,
        row_index: int,
        record: Record,
    ) -> None:
        for column_index, field_name, outcome in (
            (KEY_COLUMN_INDEX, "key", record.key_outcome()),
            (VALUE_COLUMN_INDEX, "value", record.value_outcome()),
        ):
            if outcome.error is not None:
                table.set_cell_tooltip(
                    Coordinate(row_index, column_index),
                    cls._warning_tooltip(record, field_name, outcome),
                )
            elif outcome.content is None:
                table.set_cell_tooltip(
                    Coordinate(row_index, column_index),
                    cls._null_tooltip(record, field_name),
                )

    @work(group="records-consume")
    async def consume_records(self) -> None:
        table = self.query_one(RecordDataTable)
        try:
            records = await self.consumer.consume(filters=self.filters)

            for record in records:
                record_id = str(record)
                self.records[record_id] = record
                row_index = len(table.rows)
                table.add_row(*self._record_row(record), key=record_id)
                self._add_cell_tooltips(table, row_index, record)
            self._update_table_title()
        except CONSUMER_EXCEPTIONS as ex:
            notify_error(self.app, "Consumption Error", ex)
        finally:
            table.loading = False
            self._is_consuming = False
            self.refresh_bindings()


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
        self.deserializer_factory = DeserializerPool(
            self.registry_config,
            self.protobuf_config,
            self.avro_config,
            self.json_config,
        )
        self.consumer = ConsumerService(
            self.topic,
            self.kafka_config,
            self.deserializer_factory,
            self.key_deserialization,
            self.value_deserialization,
            bytes_config=self.bytes_config,
            fallback_config=self.fallback_config,
            partitions=self.partitions,
        )

    def compose(self) -> ComposeResult:
        yield KaskadeHeader(self.kafka_config)
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
        )
        yield Footer(compact=True)
