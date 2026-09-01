from inspect import isawaitable
from typing import Any, ClassVar

from confluent_kafka import KafkaException
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container
from textual.coordinate import Coordinate
from textual.widgets import DataTable, Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from kaskade.colors import PRIMARY
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
)

CHUNKS_SHORTCUT = "#"
NEXT_SHORTCUT = "n"
SUBMIT_SHORTCUT = "enter"
BACK_SHORTCUT = "escape"
FILTER_SHORTCUT = "/,ctrl+f"
EXPORT_SHORTCUT = "ctrl+e"
COPY_RECORD_SHORTCUT = "y"
CONSUMER_EXCEPTIONS: tuple[type[Exception], ...] = (KafkaException,)
KEY_COLUMN_INDEX = 0
VALUE_COLUMN_INDEX = 1


class RecordDataTable(StretchyDataTable[str | Text]):
    """A records table with diagnostic tooltips for individual cells."""

    def __init__(self, **kwargs: Any) -> None:
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


class TopicScreen(HelpableModalScreen):
    BINDING_GROUP_TITLE = "Record Details"
    AUTO_FOCUS = ".record-details"
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            COPY_RECORD_SHORTCUT,
            "copy_record",
            "Copy Record",
            show=False,
            tooltip="Copy the record as JSON to the clipboard.",
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
            BACK_SHORTCUT,
            "close",
            "Back",
            tooltip="Close the record details.",
            id="kaskade.record-details.close",
        ),
    )

    def __init__(self, record: Record):
        super().__init__()
        self.record = record
        self.data = record.dict()

    def compose(self) -> ComposeResult:
        container = KaskadeScrollableContainer(classes="record-details")
        container.border_title = rf"[{PRIMARY}]Record[/] \[[{PRIMARY}]{self.record.topic}[/]]\[[{PRIMARY}]{self.record.partition}[/]]\[[{PRIMARY}]{self.record.offset}[/]]"
        with container:
            yield Static(record_json_renderable(self.data), classes="record-json")
        yield Footer(compact=True)

    def action_close(self) -> None:
        self.dismiss()

    def action_export_record(self) -> None:
        try:
            deliver_record(self.app, self.record)
        except DESERIALIZATION_EXCEPTIONS as ex:
            notify_error(self.app, "Deserialization Error", ex)

    def action_copy_record(self) -> None:
        try:
            copy_text(self.app, record_json(self.record).removesuffix("\n"), "record JSON")
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
        partitions: tuple[PartitionSelection, ...] = (),
        consumer: ConsumerService | None = None,
    ):
        super().__init__()
        self.topic = topic
        self.kafka_config = kafka_config
        self.deserializer_factory = deserializer_factory
        self.key_deserialization = key_deserialization
        self.value_deserialization = value_deserialization
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
        table = RecordDataTable(id="records-table", classes="kaskade-table main-table")
        table.cursor_type = "row"
        table.border_subtitle = rf"\[[{PRIMARY}]Consumer Mode[/]]"
        table.zebra_stripes = True
        table.border_title = self._get_title()

        table.add_column("Key", stretch=2)
        table.add_column("Value", stretch=3)
        table.add_column("Timestamp", width=23)
        table.add_column("Partition", width=9)
        table.add_column("Offset", width=9)
        table.add_column("Headers", width=9)

        yield table

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
            self.app.push_screen(TopicScreen(self.current_record))
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
    def _content_cell(content: str, *, warning: bool) -> str | Text:
        content = content.strip()
        if warning:
            return Text(
                f"{WARNING_INDICATOR} {content}",
                style=WARNING_STYLE,
            )
        return content

    @classmethod
    def _record_row(cls, record: Record) -> list[str | Text]:
        record.resolve_deserializations()
        return [
            cls._content_cell(
                record.key_str(),
                warning=record.key_outcome().used_fallback,
            ),
            cls._content_cell(
                record.value_str(),
                warning=record.value_outcome().used_fallback,
            ),
            record.timestamp,
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
        tooltip.append(f"\nError: {outcome.error}")
        return tooltip

    @classmethod
    def _add_warning_tooltips(
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
                self._add_warning_tooltips(table, row_index, record)
            table.border_title = self._get_title()
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
        partitions: tuple[PartitionSelection, ...] = (),
    ):
        super().__init__()
        self.topic = topic
        self.kafka_config = kafka_config
        self.registry_config = registry_config
        self.protobuf_config = protobuf_config
        self.avro_config = avro_config
        self.key_deserialization = key_deserialization
        self.value_deserialization = value_deserialization
        self.partitions = partitions
        self.deserializer_factory = DeserializerPool(
            self.registry_config,
            self.protobuf_config,
            self.avro_config,
        )
        self.consumer = ConsumerService(
            self.topic,
            self.kafka_config,
            self.deserializer_factory,
            self.key_deserialization,
            self.value_deserialization,
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
            partitions=self.partitions,
            consumer=self.consumer,
        )
        yield Footer(compact=True)
