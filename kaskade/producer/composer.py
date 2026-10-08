"""The record composer: Headers, Key, Value, and Preview tabs."""

from typing import ClassVar

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.widgets import Checkbox, DataTable, Select, Static, TabbedContent, TabPane, TextArea

from kaskade.colors import NULL, PRIMARY
from kaskade.deserializers import BytesEncoding
from kaskade.producer.screens import HeaderEntry, HeaderScreen
from kaskade.producer.source import DraftField, RecordDraft
from kaskade.producer_service import (
    DeliveryError,
    OutgoingRecord,
    ProducerService,
    ProducerSettings,
)
from kaskade.serializers import Serialization, SerializationError, SerializerPool
from kaskade.ui import notify_error
from kaskade.widgets import KaskadeScrollableContainer, StretchyDataTable

PRODUCE_SHORTCUT = "ctrl+s"
NEXT_DRAFT_SHORTCUT = "ctrl+pagedown"
PREVIOUS_DRAFT_SHORTCUT = "ctrl+pageup"
FIELDS = ("key", "value")


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
        content = TextArea(id=f"{self.field_name}-content", classes="field-content")
        content.border_title = "Content"
        yield content
        yield Static(id=f"{self.field_name}-status", classes="field-status")

    def on_mount(self) -> None:
        self.update_status()

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
        self.update_status()

    def serialize(self) -> bytes | None:
        """Return the content bytes, None for null, or raise SerializationError."""
        if self.is_null:
            return None
        return self.serializers.get(self.serialization, self.encoding).serialize(self.content.text)

    def update_status(self) -> None:
        status = self.query_one(f"#{self.field_name}-status", Static)
        try:
            data = self.serialize()
        except SerializationError as ex:
            status.update(Text(str(ex), style="error"))
            status.set_class(True, "-invalid")
            return
        status.set_class(False, "-invalid")
        status.update(
            Text("Null", style=NULL)
            if data is None
            else Text(f"Valid · {byte_size(data)}", style="success")
        )

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
        self.update_status()
        self.post_message(self.Changed())


class HeadersPane(Container):
    """Ordered headers; duplicate names, empty strings, and null values are kept."""

    BINDING_GROUP_TITLE = "Headers"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            "n,ctrl+n",
            "add_header",
            "Add Header",
            tooltip="Add a header after the existing headers.",
            id="kaskade.headers.add",
        ),
        Binding(
            "e,enter",
            "edit_header",
            "Edit Header",
            key_display="e",
            priority=True,
            tooltip="Edit the selected header.",
            id="kaskade.headers.edit",
        ),
        Binding(
            "ctrl+d,delete",
            "delete_header",
            "Delete Header",
            key_display="ctrl+d",
            tooltip="Remove the selected header.",
            id="kaskade.headers.delete",
        ),
    ]

    class Changed(Message):
        """Posted after a header is added, edited, or removed."""

    def __init__(self) -> None:
        super().__init__(id="headers-pane")
        self.headers: list[HeaderEntry] = []

    def compose(self) -> ComposeResult:
        table: StretchyDataTable[str | Text] = StretchyDataTable(
            id="headers-table", cursor_type="row", classes="details-table"
        )
        table.add_column("Name", stretch=1)
        table.add_column("Value", stretch=2)
        yield table
        yield Static("No headers. Press n to add one.", id="headers-empty")

    def on_mount(self) -> None:
        self._refresh_table()

    def load(self, headers: tuple[HeaderEntry, ...]) -> None:
        self.headers = list(headers)
        self._refresh_table()

    def _refresh_table(self, cursor_row: int | None = None) -> None:
        table = self.query_one("#headers-table", DataTable)
        table.clear()
        for name, value in self.headers:
            table.add_row(name, Text("null", style=NULL) if value is None else value)
        self.query_one("#headers-empty", Static).display = not self.headers
        if cursor_row is not None and self.headers:
            table.move_cursor(row=min(cursor_row, len(self.headers) - 1))
        self.post_message(self.Changed())

    def _selected_row(self) -> int | None:
        table = self.query_one("#headers-table", DataTable)
        return table.cursor_row if self.headers else None

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in {"edit_header", "delete_header"}:
            return None if not self.headers else True
        return True

    def action_add_header(self) -> None:
        def add(header: HeaderEntry | None) -> None:
            if header is not None:
                self.headers.append(header)
                self._refresh_table(cursor_row=len(self.headers) - 1)

        self.app.push_screen(HeaderScreen(), add)

    def action_edit_header(self) -> None:
        row = self._selected_row()
        if row is None:
            return

        def edit(header: HeaderEntry | None) -> None:
            if header is not None:
                self.headers[row] = header
                self._refresh_table(cursor_row=row)

        self.app.push_screen(HeaderScreen(self.headers[row]), edit)

    def action_delete_header(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        del self.headers[row]
        self._refresh_table(cursor_row=row)


class RecordComposer(Container):
    """Compose, preview, and produce one record at a time."""

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
    ]

    def __init__(
        self,
        settings: ProducerSettings,
        service: ProducerService,
        drafts: tuple[RecordDraft, ...] = (),
    ) -> None:
        super().__init__(id="record-composer", classes="kaskade-table")
        self.settings = settings
        self.service = service
        self.drafts = drafts
        self.draft_index = 0
        self.serializers = SerializerPool()
        self.status = Text("Producer Mode")
        self.is_producing = False

    def compose(self) -> ComposeResult:
        with TabbedContent(id="composer-tabs"):
            with TabPane("Headers [0]", id="headers-tab"):
                yield HeadersPane()
            for field_name, serialization in (
                ("key", self.settings.key_serialization),
                ("value", self.settings.value_serialization),
            ):
                with TabPane(field_name.title(), id=f"{field_name}-tab"):
                    yield FieldEditor(field_name, serialization, self.serializers)
            with (
                TabPane("Preview", id="preview-tab"),
                KaskadeScrollableContainer(id="preview-scroll"),
            ):
                yield Static(id="record-preview")

    def on_mount(self) -> None:
        if self.drafts:
            self.call_after_refresh(self.load_draft, 0)
        self._update_frame()
        self.update_preview()

    async def on_unmount(self) -> None:
        await self.service.aclose()

    def _update_frame(self) -> None:
        title = rf"[{PRIMARY}]Compose Record[/] \[[{PRIMARY}]{self.settings.topic}[/]]"
        if len(self.drafts) > 1:
            title += rf"\[[{PRIMARY}]Record {self.draft_index + 1}/{len(self.drafts)}[/]]"
        self.border_title = title
        self.border_subtitle = self.status.markup

    def set_status(self, status: Text) -> None:
        self.status = status
        self._update_frame()

    def editor(self, field_name: str) -> FieldEditor:
        return self.query_one(f"#{field_name}-editor", FieldEditor)

    def load_draft(self, index: int) -> None:
        self.draft_index = index
        draft = self.drafts[index]
        self.query_one(HeadersPane).load(draft.headers)
        self.editor("key").load(draft.key)
        self.editor("value").load(draft.value)
        self._update_frame()
        self.update_preview()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in {"next_draft", "previous_draft"}:
            return len(self.drafts) > 1
        if action == "produce":
            return None if self.is_producing else True
        return True

    def action_next_draft(self) -> None:
        self.load_draft((self.draft_index + 1) % len(self.drafts))

    def action_previous_draft(self) -> None:
        self.load_draft((self.draft_index - 1) % len(self.drafts))

    @on(HeadersPane.Changed)
    @on(FieldEditor.Changed)
    def draft_changed(self) -> None:
        headers = self.query_one(HeadersPane).headers
        self.query_one(TabbedContent).get_tab("headers-tab").label = f"Headers [{len(headers)}]"
        self.update_preview()

    def update_preview(self) -> None:
        preview = Text()
        partition = self.settings.partition
        self._preview_row(preview, "Topic", Text(self.settings.topic))
        self._preview_row(
            preview, "Partition", Text("Automatic" if partition is None else str(partition))
        )
        headers = self.query_one(HeadersPane).headers
        self._preview_row(preview, "Headers", Text(str(len(headers))))
        for name, value in headers:
            preview.append(f"  {name}: ")
            preview.append_text(Text("null", style=NULL) if value is None else Text(value))
            preview.append("\n")
        failures = [
            failure
            for field_name in FIELDS
            if (failure := self._preview_field(field_name, preview)) is not None
        ]
        status = (
            Text("; ".join(failures), style="error")
            if failures
            else Text("Ready to produce", style="success")
        )
        self._preview_row(preview, "Status", status)
        self.query_one("#record-preview", Static).update(preview)

    @staticmethod
    def _preview_row(preview: Text, label: str, value: Text) -> None:
        preview.append(f"{label:<11}", style="secondary")
        preview.append_text(value)
        preview.append("\n")

    def _preview_field(self, field_name: str, preview: Text) -> str | None:
        editor = self.editor(field_name)
        serializer = editor.serialization.name
        if editor.serialization == Serialization.BYTES:
            serializer += f" · {editor.encoding.name}"
        try:
            data = editor.serialize()
        except SerializationError as ex:
            self._preview_row(preview, field_name.title(), Text(f"{serializer} · invalid"))
            return f"{field_name.title()}: {ex}"
        if data is None:
            self._preview_row(
                preview, field_name.title(), Text(f"{serializer} · ").append("null", style=NULL)
            )
            return None
        self._preview_row(preview, field_name.title(), Text(f"{serializer} · {byte_size(data)}"))
        preview.append_text(Text(editor.content.text, style="muted"))
        preview.append("\n")
        return None

    def outgoing_record(self) -> OutgoingRecord | None:
        """Serialize the draft, or reveal the first invalid field and return None."""
        serialized: dict[str, bytes | None] = {}
        for field_name in FIELDS:
            editor = self.editor(field_name)
            try:
                serialized[field_name] = editor.serialize()
            except SerializationError as ex:
                self.query_one(TabbedContent).active = f"{field_name}-tab"
                editor.content.focus()
                editor.update_status()
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
        self.set_status(Text("Producing…"))
        self.produce(record)

    @work(group="producer-delivery")
    async def produce(self, record: OutgoingRecord) -> None:
        try:
            delivery = await self.service.produce(record)
        except DeliveryError as ex:
            self.set_status(Text(ex.failure.title(), style="error"))
            notify_error(self.app, ex.failure.title(), ex)
        else:
            self.set_status(Text(delivery.summary(), style="success"))
            self.notify(delivery.summary(), title="Record Delivered")
        finally:
            self.is_producing = False
            self.refresh_bindings()
