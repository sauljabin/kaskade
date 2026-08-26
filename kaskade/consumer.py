from typing import Any, ClassVar

from confluent_kafka import KafkaException
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container
from textual.widgets import DataTable, Footer, Input, OptionList, Pretty
from textual.widgets.option_list import Option

from kaskade.colors import PRIMARY
from kaskade.deserializers import (
    DESERIALIZATION_EXCEPTIONS,
    Deserialization,
    DeserializerPool,
)
from kaskade.help import HelpableModalScreen
from kaskade.models import Record
from kaskade.services import ConsumerService
from kaskade.themes import KaskadeApp
from kaskade.utils import notify_error
from kaskade.widgets import KaskadeOptionList, KaskadeScrollableContainer, StretchyDataTable

CHUNKS_SHORTCUT = "#"
NEXT_SHORTCUT = "n"
SUBMIT_SHORTCUT = "enter"
BACK_SHORTCUT = "escape"
FILTER_SHORTCUT = "/,ctrl+f"
CONSUMER_EXCEPTIONS: tuple[type[Exception], ...] = (
    KafkaException,
    *DESERIALIZATION_EXCEPTIONS,
)


class FilterRecordScreen(HelpableModalScreen[tuple[str, str, str, str]]):
    BINDING_GROUP_TITLE = "Filter Records"
    AUTO_FOCUS = "#key"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            BACK_SHORTCUT,
            "back",
            "Back",
            tooltip="Close the filter without applying it.",
            id="kaskade.filter-records.close",
        )
    ]

    def __init__(self) -> None:
        super().__init__()
        self.key_filter = ""
        self.value_filter = ""
        self.partition_filter = ""
        self.header_filter = ""

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


class ChunkSizeScreen(HelpableModalScreen[int]):
    BINDING_GROUP_TITLE = "Chunk Size"
    AUTO_FOCUS = "#chunk-size"
    CHUNK_SIZES = ("25", "50", "100", "500", "1000", "1500")
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            BACK_SHORTCUT,
            "close",
            "Back",
            tooltip="Keep the current chunk size.",
            id="kaskade.chunk-size.close",
        )
    ]

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

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        chunk_size = int(event.option_id) if event.option_id is not None else self.current_size
        self.dismiss(chunk_size)


class TopicScreen(HelpableModalScreen):
    BINDING_GROUP_TITLE = "Record Details"
    AUTO_FOCUS = ".record-details"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            BACK_SHORTCUT,
            "close",
            "Back",
            tooltip="Close the record details.",
            id="kaskade.record-details.close",
        )
    ]

    def __init__(self, topic: str, partition: int, offset: int, data: dict[str, Any]):
        super().__init__()
        self.data = data
        self.topic = topic
        self.partition = partition
        self.record_offset = offset

    def compose(self) -> ComposeResult:
        container = KaskadeScrollableContainer(classes="record-details")
        container.border_title = rf"[{PRIMARY}]Record[/] \[[{PRIMARY}]{self.topic}[/]]\[[{PRIMARY}]{self.partition}[/]]\[[{PRIMARY}]{self.record_offset}[/]]"
        with container:
            yield Pretty(self.data)
        yield Footer(compact=True)

    def action_close(self) -> None:
        self.dismiss()


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
        kafka_config: dict[str, str],
        deserializer_factory: DeserializerPool,
        key_deserialization: Deserialization,
        value_deserialization: Deserialization,
    ):
        super().__init__()
        self.topic = topic
        self.kafka_config = kafka_config
        self.deserializer_factory = deserializer_factory
        self.key_deserialization = key_deserialization
        self.value_deserialization = value_deserialization
        self.consumer = self._new_consumer()
        self.records: dict[str, Record] = {}
        self.current_record: Record | None = None
        self.key_filter = ""
        self.value_filter = ""
        self.partition_filter = ""
        self.header_filter = ""
        self._is_consuming = False

    def _new_consumer(self) -> ConsumerService:
        return ConsumerService(
            self.topic,
            self.kafka_config,
            self.deserializer_factory,
            self.key_deserialization,
            self.value_deserialization,
        )

    def _get_title(self) -> str:
        def style(text: str) -> str:
            return rf"\[[{PRIMARY}]{text}[/]]"

        title_filter = ""

        if self.key_filter:
            title_filter += style(f"k:*{self.key_filter}*")

        if self.value_filter:
            title_filter += style(f"v:*{self.value_filter}*")

        if self.partition_filter:
            title_filter += style(f"p:{self.partition_filter}")

        if self.header_filter:
            title_filter += style(f"h:*{self.header_filter}*")

        return rf"[{PRIMARY}]Records[/] \[[{PRIMARY}]{self.topic}[/]]{title_filter}\[[{PRIMARY}]{len(self.records)}[/]]"

    def compose(self) -> ComposeResult:
        table: StretchyDataTable[str] = StretchyDataTable(
            id="records-table", classes="kaskade-table main-table"
        )
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

    def on_unmount(self) -> None:
        self.consumer.close()

    def on_mount(self) -> None:
        self.query_one("#records-table", DataTable).focus()
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
            self.app.push_screen(
                TopicScreen(
                    self.current_record.topic,
                    self.current_record.partition,
                    self.current_record.offset,
                    self.current_record.dict(),
                )
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
        if action == "show_message":
            return self.current_record is not None
        if action == "all":
            return not self._is_consuming and any(
                (self.key_filter, self.value_filter, self.partition_filter, self.header_filter)
            )
        if action in {"change_chunk", "consume", "filter"}:
            return not self._is_consuming
        return True

    def action_consume(self) -> None:
        """Start consuming unless a request is already running."""
        if not self._is_consuming:
            self.consume_records()

    @work(group="records-consume")
    async def consume_records(self) -> None:
        table = self.query_one(DataTable)
        self._is_consuming = True
        self.refresh_bindings()
        table.loading = True

        try:
            records = await self.consumer.consume(
                partition_filter=int(self.partition_filter) if self.partition_filter else None,
                key_filter=self.key_filter if self.key_filter else None,
                value_filter=self.value_filter if self.value_filter else None,
                header_filter=self.header_filter if self.header_filter else None,
            )

            for record in records:
                record_id = str(record)
                self.records[record_id] = record
                row = [
                    record.key_str().strip(),
                    record.value_str().strip(),
                    record.date,
                    str(record.partition),
                    str(record.offset),
                    str(record.headers_count()),
                ]
                table.add_row(*row, key=record_id)
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
    CSS_PATH = "styles.css"

    def __init__(
        self,
        topic: str,
        kafka_config: dict[str, str],
        registry_config: dict[str, str],
        protobuf_config: dict[str, str],
        avro_config: dict[str, str],
        key_deserialization: Deserialization,
        value_deserialization: Deserialization,
    ):
        super().__init__()
        self.topic = topic
        self.kafka_config = kafka_config
        self.registry_config = registry_config
        self.protobuf_config = protobuf_config
        self.avro_config = avro_config
        self.key_deserialization = key_deserialization
        self.value_deserialization = value_deserialization

    def compose(self) -> ComposeResult:
        yield ListRecords(
            self.topic,
            self.kafka_config,
            DeserializerPool(self.registry_config, self.protobuf_config, self.avro_config),
            self.key_deserialization,
            self.value_deserialization,
        )
        yield Footer(compact=True)
