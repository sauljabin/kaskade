"""The record composer: Headers, Key, and Value tabs and a Summary panel."""

from dataclasses import replace
from typing import ClassVar

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Grid, Horizontal
from textual.markup import escape
from textual.message import Message
from textual.widgets import Checkbox, Input, Select, Static, TabbedContent, TabPane, TextArea

from kaskade.colors import PRIMARY
from kaskade.deserializers import BytesEncoding
from kaskade.producer.source import DraftField, RecordDraft
from kaskade.producer_service import (
    DeliveryError,
    OutgoingRecord,
    ProducerService,
    ProducerSettings,
)
from kaskade.serializers import Serialization, SerializationError, SerializerPool
from kaskade.ui import notify_error
from kaskade.widgets import KaskadeScrollableContainer, MetadataCell

PRODUCE_SHORTCUT = "ctrl+s,ctrl+shift+s,f2"
SUMMARY_SHORTCUT = "f3"
SUMMARY_MIN_TERMINAL_WIDTH = 80
NEXT_DRAFT_SHORTCUT = "ctrl+pagedown,alt+pagedown"
PREVIOUS_DRAFT_SHORTCUT = "ctrl+pageup,alt+pageup"
FIELDS = ("key", "value")
HeaderEntry = tuple[str, str | None]


def without_ctrl_c_copy(bindings: list[BindingType]) -> list[BindingType]:
    """Keep a widget's copy binding on super+c only; ctrl+c belongs to Quit."""
    return [
        (
            replace(binding, key="super+c")
            if isinstance(binding, Binding) and binding.action == "copy"
            else binding
        )
        for binding in bindings
    ]


class ContentArea(TextArea, inherit_bindings=False):
    """A text editor without Textual's ctrl+c copy alias."""

    BINDINGS: ClassVar[list[BindingType]] = without_ctrl_c_copy(TextArea.BINDINGS)


class HeaderInput(Input, inherit_bindings=False):
    """A header field without Textual's ctrl+c copy alias."""

    BINDINGS: ClassVar[list[BindingType]] = without_ctrl_c_copy(Input.BINDINGS)


def byte_size(data: bytes) -> str:
    return f"{len(data)} byte{'' if len(data) == 1 else 's'}"


class FieldEditor(Container):
    """Serializer, null control, content editor, and validation for the Key or Value."""

    class Changed(Message):
        """Posted whenever the serializer, null control, or content changes."""

    def __init__(
        self, field_name: str, serialization: Serialization, serializers: SerializerPool
    ) -> None:
        super().__init__(id=f"{field_name}-editor", classes="field-editor")
        self.field_name = field_name
        self.initial_serialization = serialization
        self.serializers = serializers

    def compose(self) -> ComposeResult:
        with Horizontal(classes="field-options"):
            serializer = Select(
                [(name.upper(), name) for name in Serialization.str_list()],
                value=str(self.initial_serialization),
                allow_blank=False,
                id=f"{self.field_name}-serializer",
                classes="field-serializer",
            )
            yield serializer
            encoding = Select(
                [(str(encoding).upper(), str(encoding)) for encoding in BytesEncoding],
                value=str(BytesEncoding.BASE64),
                allow_blank=False,
                id=f"{self.field_name}-encoding",
                classes="field-encoding",
            )
            encoding.display = self.initial_serialization == Serialization.BYTES
            yield encoding
            yield Checkbox("Null", False, id=f"{self.field_name}-null", classes="field-null")
        yield Static(Text("CONTENT", style="muted"), classes="field-content-label")
        yield ContentArea(id=f"{self.field_name}-content", classes="field-content")

    @property
    def serialization(self) -> Serialization:
        value = self.query_one(f"#{self.field_name}-serializer", Select).value
        return Serialization.from_str(str(value))

    @property
    def encoding(self) -> BytesEncoding:
        value = self.query_one(f"#{self.field_name}-encoding", Select).value
        return BytesEncoding.from_str(str(value))

    @property
    def is_null(self) -> bool:
        return self.query_one(f"#{self.field_name}-null", Checkbox).value

    @property
    def content(self) -> TextArea:
        return self.query_one(f"#{self.field_name}-content", TextArea)

    def load(self, draft_field: DraftField) -> None:
        self.query_one(f"#{self.field_name}-null", Checkbox).value = draft_field.is_null
        serializer = self.serializers.get(self.serialization, self.encoding)
        text = "" if draft_field.is_null else serializer.draft_text(draft_field.content)
        self.content.load_text(text)
        self.mark_validity()

    def serialize(self) -> bytes | None:
        """Return the content bytes, None for null, or raise SerializationError."""
        if self.is_null:
            return None
        return self.serializers.get(self.serialization, self.encoding).serialize(self.content.text)

    def validation(self) -> tuple[str, bool]:
        """Return a short validation message and whether the content is invalid."""
        try:
            data = self.serialize()
        except SerializationError as ex:
            return str(ex), True
        return ("Null" if data is None else f"Valid · {byte_size(data)}"), False

    @on(Select.Changed)
    @on(Checkbox.Changed)
    @on(TextArea.Changed)
    def changed(self, event: Message) -> None:
        event.stop()
        if isinstance(event, Select.Changed):
            self.query_one(f"#{self.field_name}-encoding", Select).display = (
                self.serialization == Serialization.BYTES
            )
        if isinstance(event, Checkbox.Changed):
            self.content.disabled = event.value
        self.mark_validity()
        self.post_message(self.Changed())

    def mark_validity(self) -> None:
        """Tint the content editor while its content doesn't serialize."""
        self.set_class(self.validation()[1], "-invalid")


class HeaderRow(Horizontal):
    """One editable header: a name, a UTF-8 value, and a null control."""

    def __init__(self, header: HeaderEntry = ("", "")) -> None:
        super().__init__(classes="header-row")
        self.header = header

    def compose(self) -> ComposeResult:
        name, value = self.header
        yield HeaderInput(name, placeholder="Name", compact=True, classes="header-name column-name")
        value_input = HeaderInput(
            value or "", placeholder="Value", compact=True, classes="header-value column-value"
        )
        value_input.disabled = value is None
        yield value_input
        yield Checkbox(
            "",
            value is None,
            compact=True,
            tooltip="Send this header with a null value.",
            classes="header-null column-null",
        )

    @property
    def name_input(self) -> Input:
        return self.query_one(".header-name", Input)

    @property
    def entry(self) -> HeaderEntry:
        value: str | None = self.query_one(".header-value", Input).value
        if self.query_one(".header-null", Checkbox).value:
            value = None
        return self.name_input.value, value

    @property
    def is_blank(self) -> bool:
        return self.entry == ("", "")

    @property
    def is_unnamed(self) -> bool:
        """A header with a value or null but no name, which Kafka can't identify."""
        return not self.is_blank and not self.name_input.value


class HeadersPane(Container):
    """Postman-style headers: typing in the last, empty row adds another.

    Order, duplicate names, empty strings, and null values are kept.
    """

    BINDING_GROUP_TITLE = "Headers"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            "ctrl+d",
            "delete_header",
            "Delete Header",
            priority=True,
            tooltip="Remove the header that has focus.",
            id="kaskade.headers.delete",
        ),
    ]

    class Changed(Message):
        """Posted after a header is added, edited, or removed."""

    def __init__(self) -> None:
        super().__init__(id="headers-pane")

    def compose(self) -> ComposeResult:
        with Horizontal(classes="header-row header-labels"):
            for label in ("NAME", "VALUE", "NULL"):
                yield Static(Text(label, style="muted"), classes=f"column-{label.lower()}")
        with KaskadeScrollableContainer(id="header-rows", can_focus=False):
            yield HeaderRow()

    @property
    def rows(self) -> list[HeaderRow]:
        return list(self.query(HeaderRow))

    @property
    def headers(self) -> list[HeaderEntry]:
        return [row.entry for row in self.rows if not row.is_blank]

    def unnamed_row(self) -> HeaderRow | None:
        """Return the first header that has a value or null but no name."""
        return next((row for row in self.rows if row.is_unnamed), None)

    def unnamed_message(self) -> str | None:
        """Name the first header that needs a name, counting from 1."""
        row = self.unnamed_row()
        return None if row is None else f"Header {self.rows.index(row) + 1} needs a name"

    def _changed(self) -> None:
        """Highlight unnamed headers, then tell the composer the headers changed."""
        for row in self.rows:
            row.set_class(row.is_unnamed, "-invalid")
            row.name_input.placeholder = "Name required" if row.is_unnamed else "Name"
        self.post_message(self.Changed())

    async def load(self, headers: tuple[HeaderEntry, ...]) -> None:
        container = self.query_one("#header-rows")
        await container.remove_children()
        await container.mount_all([*(HeaderRow(header) for header in headers), HeaderRow()])
        self._changed()

    @on(Input.Changed)
    @on(Checkbox.Changed)
    async def header_changed(self, event: Input.Changed | Checkbox.Changed) -> None:
        event.stop()
        if isinstance(event, Checkbox.Changed):
            row = next(
                ancestor for ancestor in event.checkbox.ancestors if isinstance(ancestor, HeaderRow)
            )
            row.query_one(".header-value", Input).disabled = event.value
        if not self.rows[-1].is_blank:
            await self.query_one("#header-rows").mount(HeaderRow())
        self._changed()

    async def action_delete_header(self) -> None:
        focused = self.screen.focused
        row = next(
            (
                node
                for node in (focused.ancestors_with_self if focused else [])
                if isinstance(node, HeaderRow)
            ),
            None,
        )
        if row is None:
            return
        rows = self.rows
        if row is rows[-1]:
            await row.remove()
            await self.query_one("#header-rows").mount(HeaderRow())
        else:
            following = rows[rows.index(row) + 1]
            await row.remove()
            following.name_input.focus()
        self._changed()


class RecordComposer(Horizontal):
    """Compose, summarize, and produce one record at a time."""

    BINDING_GROUP_TITLE = "Compose Record"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            PRODUCE_SHORTCUT,
            "produce",
            "Produce",
            priority=True,
            tooltip="Validate, serialize, and produce the record, then wait for the broker.",
            id="kaskade.compose.produce",
        ),
        Binding(
            NEXT_DRAFT_SHORTCUT,
            "next_draft",
            "Next Record",
            key_display="ctrl+pgdn",
            priority=True,
            tooltip="Load the next record from the source file.",
            id="kaskade.compose.next",
        ),
        Binding(
            PREVIOUS_DRAFT_SHORTCUT,
            "previous_draft",
            "Previous Record",
            key_display="ctrl+pgup",
            priority=True,
            tooltip="Load the previous record from the source file.",
            id="kaskade.compose.previous",
        ),
        Binding(
            SUMMARY_SHORTCUT,
            "toggle_summary",
            "Summary",
            priority=True,
            tooltip="Show or hide the record summary panel.",
            id="kaskade.compose.summary",
        ),
    ]

    def __init__(
        self,
        settings: ProducerSettings,
        service: ProducerService,
        drafts: tuple[RecordDraft, ...] = (),
    ) -> None:
        super().__init__(id="record-composer")
        self.settings = settings
        self.service = service
        self.drafts = drafts
        self.draft_index = 0
        self.serializers = SerializerPool()
        self.delivery_status = ""
        self.is_producing = False

    def compose(self) -> ComposeResult:
        with (
            Container(id="composer-frame", classes="kaskade-table"),
            TabbedContent(id="composer-tabs"),
        ):
            for field_name, serialization in (
                ("key", self.settings.key_serialization),
                ("value", self.settings.value_serialization),
            ):
                with TabPane(field_name.title(), id=f"{field_name}-tab"):
                    yield FieldEditor(field_name, serialization, self.serializers)
            with TabPane("Headers [0]", id="headers-tab"):
                yield HeadersPane()
        summary = KaskadeScrollableContainer(id="record-summary", can_focus=False)
        summary.border_title = f"[{PRIMARY}]Summary[/]"
        with summary:
            with Grid(id="summary-metadata", classes="summary-grid"):
                yield MetadataCell(
                    "Topic", self.settings.topic, ellipsize_value=True, id="summary-topic"
                )
                yield MetadataCell("Partition", "", ellipsize_value=True, id="summary-partition")
                yield MetadataCell("Headers", "", ellipsize_value=True, id="summary-headers")
            for field_name in FIELDS:
                yield Static(Text(field_name.upper(), style="muted"), classes="summary-label")
                with Grid(classes="summary-grid summary-field"):
                    yield MetadataCell(
                        "Serializer",
                        "",
                        ellipsize_value=True,
                        id=f"summary-{field_name}-serializer",
                    )
                    yield MetadataCell(
                        "Size", "", ellipsize_value=True, id=f"summary-{field_name}-size"
                    )
            yield Static(id="summary-status")

    def on_mount(self) -> None:
        self.query_one("#record-summary").display = (
            self.app.size.width >= SUMMARY_MIN_TERMINAL_WIDTH
        )
        if self.drafts:
            self.call_after_refresh(self.load_draft, 0)
        self._update_frame()
        self.update_summary()

    async def on_unmount(self) -> None:
        await self.service.aclose()

    def _update_frame(self) -> None:
        title = rf"[{PRIMARY}]Compose Record[/] \[[{PRIMARY}]{self.settings.topic}[/]]"
        if len(self.drafts) > 1:
            title += rf"\[[{PRIMARY}]Record {self.draft_index + 1}/{len(self.drafts)}[/]]"
        self.frame.border_title = title
        parts = ["Producer Mode"]
        active_field = self.query_one(TabbedContent).active.removesuffix("-tab")
        if active_field in FIELDS:
            message, invalid = self.editor(active_field).validation()
            field_status = f"{active_field.title()} {escape(message)}"
            parts.append(f"[$text-error]{field_status}[/]" if invalid else field_status)
        elif (unnamed := self.query_one(HeadersPane).unnamed_message()) is not None:
            parts.append(f"[$text-error]{unnamed}[/]")
        if self.delivery_status:
            parts.append(self.delivery_status)
        self.frame.border_subtitle = rf"\[[{PRIMARY}]{' · '.join(parts)}[/]]"

    @property
    def frame(self) -> Container:
        """The bordered frame around the tabs; the Summary sits beside it."""
        return self.query_one("#composer-frame", Container)

    def set_delivery_status(self, status: str, *, failed: bool = False) -> None:
        self.delivery_status = f"[$text-error]{escape(status)}[/]" if failed else escape(status)
        self._update_frame()

    @on(TabbedContent.TabActivated)
    def tab_activated(self) -> None:
        self._update_frame()

    def editor(self, field_name: str) -> FieldEditor:
        return self.query_one(f"#{field_name}-editor", FieldEditor)

    async def load_draft(self, index: int) -> None:
        self.draft_index = index
        draft = self.drafts[index]
        await self.query_one(HeadersPane).load(draft.headers)
        self.editor("key").load(draft.key)
        self.editor("value").load(draft.value)
        self._update_frame()
        self.update_summary()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in {"next_draft", "previous_draft"}:
            return len(self.drafts) > 1
        if action == "produce":
            return None if self.is_producing else True
        return True

    async def action_next_draft(self) -> None:
        await self.load_draft((self.draft_index + 1) % len(self.drafts))

    async def action_previous_draft(self) -> None:
        await self.load_draft((self.draft_index - 1) % len(self.drafts))

    @on(HeadersPane.Changed)
    @on(FieldEditor.Changed)
    def draft_changed(self) -> None:
        headers = self.query_one(HeadersPane).headers
        self.query_one(TabbedContent).get_tab("headers-tab").label = f"Headers [{len(headers)}]"
        self.update_summary()
        self._update_frame()

    def update_summary(self) -> None:
        partition = self.settings.partition
        self._summary_cell("partition").update_value(
            "Automatic" if partition is None else str(partition)
        )
        self._summary_cell("headers").update_value(str(len(self.query_one(HeadersPane).headers)))
        invalid = [
            field_name.title() for field_name in FIELDS if not self._summarize_field(field_name)
        ]
        if self.query_one(HeadersPane).unnamed_row() is not None:
            invalid.append("Headers")
        status = self.query_one("#summary-status", Static)
        status.set_class(bool(invalid), "-invalid")
        status.update(f"Invalid {' and '.join(invalid)}" if invalid else "Ready to produce")

    def _summary_cell(self, name: str) -> MetadataCell:
        return self.query_one(f"#summary-{name}", MetadataCell)

    def _summarize_field(self, field_name: str) -> bool:
        """Show the field's serializer and size; return whether it serializes."""
        editor = self.editor(field_name)
        serializer = editor.serialization.name
        if editor.serialization == Serialization.BYTES:
            serializer += f" · {editor.encoding.name}"
        self._summary_cell(f"{field_name}-serializer").update_value(serializer)
        size = self._summary_cell(f"{field_name}-size")
        try:
            data = editor.serialize()
        except SerializationError:
            size.update_value("Invalid")
            return False
        size.update_value("Null" if data is None else byte_size(data))
        return True

    def action_toggle_summary(self) -> None:
        summary = self.query_one("#record-summary")
        summary.display = not summary.display

    def outgoing_record(self) -> OutgoingRecord | None:
        """Serialize the draft, or reveal the first invalid field and return None."""
        headers = self.query_one(HeadersPane)
        unnamed = headers.unnamed_row()
        if unnamed is not None:
            self.query_one(TabbedContent).active = "headers-tab"
            unnamed.name_input.focus()
            self.notify(str(headers.unnamed_message()), title="Invalid Header", severity="warning")
            return None
        serialized: dict[str, bytes | None] = {}
        for field_name in FIELDS:
            editor = self.editor(field_name)
            try:
                serialized[field_name] = editor.serialize()
            except SerializationError as ex:
                self.query_one(TabbedContent).active = f"{field_name}-tab"
                editor.content.focus()
                self.notify(
                    f"{field_name.title()}: {ex}", title="Serialization Error", severity="warning"
                )
                return None
        return OutgoingRecord(
            key=serialized["key"],
            value=serialized["value"],
            headers=tuple(self.query_one(HeadersPane).headers),
            partition=self.settings.partition,
        )

    def action_produce(self) -> None:
        if self.is_producing:
            return
        record = self.outgoing_record()
        if record is None:
            return
        self.is_producing = True
        self.refresh_bindings()
        self.set_delivery_status("Producing…")
        self.produce(record)

    @work(group="producer-delivery")
    async def produce(self, record: OutgoingRecord) -> None:
        try:
            delivery = await self.service.produce(record)
        except DeliveryError as ex:
            self.set_delivery_status(ex.failure.title(), failed=True)
            notify_error(self.app, ex.failure.title(), ex)
        else:
            self.set_delivery_status(delivery.summary())
            self.notify(delivery.summary(), title="Record Delivered")
        finally:
            self.is_producing = False
            self.refresh_bindings()
