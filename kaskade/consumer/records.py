"""The consumed records list."""

from inspect import isawaitable
from typing import Any, ClassVar

from confluent_kafka import KafkaException
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container
from textual.coordinate import Coordinate
from textual.widgets import DataTable

from kaskade.colors import NULL, PRIMARY, WARNING
from kaskade.commands import RecordFilters
from kaskade.consumer.details import (
    COPY_RECORD_SHORTCUT,
    EXPORT_SHORTCUT,
    NEXT_SHORTCUT,
    TopicScreen,
    format_payload_size,
    record_payload_size,
)
from kaskade.consumer.screens import (
    BACK_SHORTCUT,
    SUBMIT_SHORTCUT,
    ChunkSizeScreen,
    FilterRecordScreen,
)
from kaskade.consumer_service import ConsumerService, PartitionSelectionError
from kaskade.deserializers import (
    DESERIALIZATION_EXCEPTIONS,
    Deserialization,
    DeserializerPool,
)
from kaskade.models import DeserializationOutcome, PartitionSelection, Record
from kaskade.record_export import deliver_record, record_json
from kaskade.timeouts import TimeoutConfig
from kaskade.ui import copy_text, notify_error
from kaskade.unicodes import WARNING_SIGN
from kaskade.widgets import StretchyDataTable, TableFrame

CHUNKS_SHORTCUT = "#"
FILTER_SHORTCUT = "/,ctrl+f"
CONSUMER_EXCEPTIONS: tuple[type[Exception], ...] = (KafkaException, PartitionSelectionError)
KEY_COLUMN_INDEX = 0
VALUE_COLUMN_INDEX = 1


def new_consumer(
    topic: str,
    kafka_config: dict[str, Any],
    deserializer_factory: DeserializerPool,
    key_deserialization: Deserialization,
    value_deserialization: Deserialization,
    *,
    bytes_config: dict[str, str],
    fallback_config: dict[str, str],
    partitions: tuple[PartitionSelection, ...],
    timeouts: TimeoutConfig,
) -> ConsumerService:
    """Build the consumer the app starts and a filter change rebuilds."""
    return ConsumerService(
        topic,
        kafka_config,
        deserializer_factory,
        key_deserialization,
        value_deserialization,
        bytes_config=bytes_config,
        fallback_config=fallback_config,
        partitions=partitions,
        timeouts=timeouts,
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
        timeouts: TimeoutConfig | None = None,
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
        self.timeouts = timeouts or TimeoutConfig()
        self.consumer = consumer or self._new_consumer()
        self.records: dict[str, Record] = {}
        self.current_record: Record | None = None
        self.filters = RecordFilters()
        self._is_consuming = False

    def _new_consumer(self) -> ConsumerService:
        return new_consumer(
            self.topic,
            self.kafka_config,
            self.deserializer_factory,
            self.key_deserialization,
            self.value_deserialization,
            bytes_config=self.bytes_config,
            fallback_config=self.fallback_config,
            partitions=self.partitions,
            timeouts=self.timeouts,
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

        return (
            rf"[{PRIMARY}]Records[/] \[[{PRIMARY}]{self.topic}[/]]{title_filter}"
            rf"\[[{PRIMARY}]{len(self.records)}[/]]"
        )

    def _get_subtitle(self) -> str:
        group_id = getattr(self.consumer, "group_id", None)
        description = (
            f"Consumer Mode · Group {group_id}"
            if isinstance(group_id, str) and group_id
            else "Consumer Mode"
        )
        return rf"\[[{PRIMARY}]{description}[/]]"

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
        frame.border_subtitle = self._get_subtitle()
        yield frame

    async def on_unmount(self) -> None:
        try:
            result = self.consumer.aclose()
            if isawaitable(result):
                await result
        finally:
            self.deserializer_factory.close()

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
        table.loading = True
        self.records = {}
        self.current_record = None
        self._is_consuming = True
        self.refresh_bindings()
        self._update_table_title()
        self.replace_consumer()

    @work(group="records-consume")
    async def replace_consumer(self) -> None:
        """Restart consumption from the configured position without blocking the UI."""
        previous = self.consumer
        try:
            self.consumer = self._new_consumer()
            self.query_one("#records-frame", TableFrame).border_subtitle = self._get_subtitle()
            await previous.aclose()
        except CONSUMER_EXCEPTIONS as ex:
            notify_error(self.app, "Consumer Error", ex)
        finally:
            self._is_consuming = False
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
                f"{WARNING_SIGN} {content}",
                style=WARNING,
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
            f"{WARNING_SIGN} {field_name.title()} Deserialization Warning",
            style=WARNING,
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
        tooltip.append(f"Null {field_name.title()}", style=WARNING)
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
