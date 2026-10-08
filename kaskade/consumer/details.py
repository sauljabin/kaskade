"""The record details screen and its key, value, and header panels."""

from collections.abc import Callable
from typing import Any, ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Grid
from textual.content import Content
from textual.widgets import DataTable, Footer, Static, TabbedContent, TabPane

from kaskade.colors import PRIMARY, WARNING
from kaskade.consumer.screens import BACK_SHORTCUT
from kaskade.deserializers import DESERIALIZATION_EXCEPTIONS, Deserialization
from kaskade.help import HelpableModalScreen, modal_bindings
from kaskade.models import DeserializationOutcome, Record
from kaskade.record_export import deliver_record, readable_json, record_json_renderable
from kaskade.ui import copy_text, notify_error
from kaskade.widgets import (
    KaskadeScrollableContainer,
    MetadataCell,
    TruncatedTooltipDataTable,
    labelled_value,
)

NEXT_SHORTCUT = "n"
PREVIOUS_SHORTCUT = "N,p"
EXPORT_SHORTCUT = "ctrl+e"
COPY_RECORD_SHORTCUT = "y"
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


class HeaderDataTable(TruncatedTooltipDataTable[str | Text]):
    """A compact header table that reveals truncated header names."""

    TOOLTIP_COLUMNS = frozenset({"name"})


class RecordFieldDetails(Container):
    """Keep field diagnostics separate from independently scrollable content."""

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

    def _header_summary(self) -> Text:
        summary = labelled_value("Header", self.field_name or "")
        summary.append(f" · {format_payload_size(self.payload_size)}", style="muted")
        return summary

    def _content_label(self) -> Text:
        if self.payload_size is None:
            label = "No Content (Null)"
        else:
            label = "FALLBACK CONTENT" if self.outcome.error is not None else "CONTENT"
        return Text(label, style="muted")

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
                style=WARNING,
            )
        return error

    def compose(self) -> ComposeResult:
        with KaskadeScrollableContainer(classes="record-field-metadata", can_focus=False):
            field_name = Static(classes="record-field-name")
            field_name.display = self.field_name is not None
            if self.field_name is not None:
                field_name.update(self._header_summary())
            yield field_name

            diagnostics = Grid(classes="record-diagnostics")
            diagnostics.display = self.field_name is None
            with diagnostics:
                yield MetadataCell(
                    "Deserializer",
                    self._deserializer(),
                    classes="record-diagnostic record-deserializer",
                )
                yield MetadataCell(
                    "Schema",
                    self._schema(),
                    classes="record-diagnostic record-schema",
                )
                yield MetadataCell(
                    "Size",
                    format_payload_size(self.payload_size),
                    classes="record-diagnostic record-size",
                )

            error = Static(self._error(), classes="record-error")
            error.display = self.outcome.error is not None
            yield error
        yield Static(self._content_label(), classes="record-content-label")
        content_area = Container(classes="record-content-area")
        content_area.display = self.payload_size is not None
        with (
            content_area,
            KaskadeScrollableContainer(classes="record-detail-scroll record-content-scroll"),
        ):
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
            name.update(self._header_summary())
        self.query_one(".record-diagnostics", Grid).display = field_name is None
        self.query_one(".record-deserializer", MetadataCell).update_value(self._deserializer())
        self.query_one(".record-schema", MetadataCell).update_value(self._schema())
        self.query_one(".record-size", MetadataCell).update_value(
            format_payload_size(self.payload_size)
        )
        error = self.query_one(".record-error", Static)
        error.display = outcome.error is not None
        error.update(self._error())
        self.query_one(".record-content-label", Static).update(self._content_label())
        self.query_one(".record-content-area", Container).display = payload_size is not None
        self.query_one(".record-content", Static).update(
            record_json_renderable(outcome.dict()["content"])
        )
        self.query_one(".record-field-metadata", KaskadeScrollableContainer).scroll_home(
            animate=False
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

    def _headers_table(self) -> HeaderDataTable:
        headers = HeaderDataTable(
            id="record-headers-list",
            show_header=False,
            cursor_type="row",
        )
        max_header_index = max(
            (len(record.headers) - 1 for record in self.records),
            default=0,
        )
        index_width = len(str(max(0, max_header_index)))
        headers.add_column("", key="index", width=index_width)
        headers.add_column("", key="name", width=1, stretch=1)
        self._add_header_rows(headers)
        return headers

    def _add_header_rows(self, headers: HeaderDataTable) -> None:
        for index, header in enumerate(self.record.headers):
            headers.add_row(Text(str(index), style="muted"), header.key, key=str(index))

    def compose(self) -> ComposeResult:
        container = Container(classes="record-details")
        container.border_title = self._title()
        with container:
            with Grid(id="record-metadata"):
                for metadata_id, label, value in self._metadata():
                    yield MetadataCell(
                        label,
                        value,
                        id=metadata_id,
                        classes="record-metadata-cell",
                    )
            with TabbedContent(initial="key", id="record-details-tabs"):
                with TabPane("Key", id="key"):
                    yield RecordFieldDetails(
                        self.record.key_outcome(),
                        payload_size=(
                            len(self.record.key) if self.record.key is not None else None
                        ),
                        id="record-key-details",
                    )
                with TabPane("Value", id="value"):
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
                    headers = self._headers_table()
                    headers.display = bool(self.record.headers)
                    yield headers
                    empty = Static("No headers", id="record-headers-empty")
                    empty.display = not self.record.headers
                    yield empty
                    header_details = Container(classes="record-header-details")
                    header_details.display = bool(self.record.headers)
                    with header_details:
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
                    TabPane("Export", id="json"),
                    Container(classes="record-content-area"),
                    KaskadeScrollableContainer(
                        classes="record-detail-scroll record-content-scroll"
                    ),
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
        for metadata_id, _, value in self._metadata():
            self.query_one(f"#{metadata_id}", MetadataCell).update_value(value)
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
        headers = self.query_one("#record-headers-list", HeaderDataTable)
        empty = self.query_one("#record-headers-empty", Static)
        details = self.query_one(".record-header-details", Container)
        headers.clear()
        has_headers = bool(self.record.headers)
        headers.display = has_headers
        empty.display = not has_headers
        details.display = has_headers
        if has_headers:
            self._add_header_rows(headers)
            headers.move_cursor(row=0)
            header = self.record.headers[0]
            self.query_one("#record-header-details", RecordFieldDetails).update_outcome(
                header.value_outcome(),
                payload_size=len(header.value) if header.value is not None else None,
                field_name=header.key,
            )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if (
            event.data_table.id != "record-headers-list"
            or event.row_key is None
            or event.row_key.value is None
        ):
            return
        header = self.record.headers[int(event.row_key.value)]
        self.query_one("#record-header-details", RecordFieldDetails).update_outcome(
            header.value_outcome(),
            payload_size=len(header.value) if header.value is not None else None,
            field_name=header.key,
        )
        self.query_one(
            "#record-header-details .record-content-scroll", KaskadeScrollableContainer
        ).scroll_home(animate=False)

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
