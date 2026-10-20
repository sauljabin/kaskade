"""The record composer: Headers, Key, and Value tabs and a Summary panel."""

from dataclasses import replace
from typing import Any, ClassVar

from rich.table import Table
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Grid, Horizontal
from textual.markup import escape
from textual.message import Message
from textual.widgets import Checkbox, Input, Static, TabbedContent, TabPane, TextArea

from kaskade.apicurio import APICURIO_USE_ID
from kaskade.colors import PRIMARY
from kaskade.concurrency import run_blocking
from kaskade.configs import (
    ACKS,
    APICURIO_OPTION,
    COMPRESSION_TYPE,
    CONFLUENT_OPTION,
    ENABLE_IDEMPOTENCE,
)
from kaskade.producer.highlighting import (
    JSON_HIGHLIGHT_QUERY,
    JSON_LANGUAGE,
    json_language,
    json_theme,
)
from kaskade.producer.source import DraftField, RecordDraft
from kaskade.producer_service import (
    DeliveryError,
    OutgoingRecord,
    ProducerService,
    ProducerSettings,
)
from kaskade.serializers import Serialization, SerializationError, Serializer, SerializerPool
from kaskade.ui import format_size, notify_error
from kaskade.widgets import KaskadeScrollableContainer, MetadataCell

PRODUCE_SHORTCUT = "ctrl+s,ctrl+shift+s,f2"
SUMMARY_SHORTCUT = "f3"
SUMMARY_MIN_TERMINAL_WIDTH = 80
FIELDS = ("key", "value")
CLIENT_SETTINGS = (
    ("Acks", ACKS),
    ("Idempotence", ENABLE_IDEMPOTENCE),
    ("Compression", COMPRESSION_TYPE),
)
HeaderEntry = tuple[str, str | None]
Problem = tuple[str, str]
"""A label, such as Key or Header 2, and what is wrong with it."""


def problem_text(problem: Problem) -> str:
    label, message = problem
    return f"{label}: {message}"


def problem_table(problems: list[Problem]) -> Table:
    """Align bold labels in one column so each problem is easy to find."""
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold", no_wrap=True)
    table.add_column()
    for label, message in problems:
        table.add_row(label, message)
    return table


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
    """A text editor without Textual's ctrl+c copy alias, with optional JSON highlighting."""

    BINDINGS: ClassVar[list[BindingType]] = without_ctrl_c_copy(TextArea.BINDINGS)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.register_language(JSON_LANGUAGE, json_language(), JSON_HIGHLIGHT_QUERY)

    def on_mount(self) -> None:
        self.refresh_json_theme()
        self.app.theme_changed_signal.subscribe(self, lambda _: self.refresh_json_theme())

    def refresh_json_theme(self) -> None:
        theme = json_theme(self.app)
        self.register_theme(theme)
        self.theme = theme.name

    def highlight_json(self, enabled: bool) -> None:
        self.language = JSON_LANGUAGE if enabled else None


class HeaderInput(Input, inherit_bindings=False):
    """A header field without Textual's ctrl+c copy alias."""

    BINDINGS: ClassVar[list[BindingType]] = without_ctrl_c_copy(Input.BINDINGS)


class FieldEditor(Container):
    """Null control, content editor, and validation for the Key or Value.

    The serializer comes from -k or -v and stays fixed while the producer runs.
    """

    class Changed(Message):
        """Posted whenever the null control or content changes."""

    def __init__(self, field_name: str, serializer: Serializer) -> None:
        super().__init__(id=f"{field_name}-editor", classes="field-editor")
        self.field_name = field_name
        self.serializer = serializer

    def compose(self) -> ComposeResult:
        with Horizontal(classes="field-options"):
            yield Checkbox("Null", False, id=f"{self.field_name}-null", classes="field-null")
        yield Static(Text("CONTENT", style="muted"), classes="field-content-label")
        yield ContentArea(id=f"{self.field_name}-content", classes="field-content")

    @property
    def is_null(self) -> bool:
        return self.query_one(f"#{self.field_name}-null", Checkbox).value

    @property
    def content(self) -> ContentArea:
        return self.query_one(f"#{self.field_name}-content", ContentArea)

    def on_mount(self) -> None:
        self.content.highlight_json(self.serializer.edits_json)

    def load(self, draft_field: DraftField) -> None:
        self.query_one(f"#{self.field_name}-null", Checkbox).value = draft_field.is_null
        text = "" if draft_field.is_null else self.serializer.draft_text(draft_field.content)
        self.content.load_text(text)
        self.mark_validity()

    def serialize(self) -> bytes | None:
        """Return the content bytes, None for null, or raise SerializationError."""
        if self.is_null:
            return None
        return self.serializer.serialize(self.content.text)

    def validation(self) -> tuple[str, bool]:
        """Return a short validation message and whether the content is invalid."""
        try:
            data = self.serialize()
        except SerializationError as ex:
            return str(ex), True
        return ("Null" if data is None else format_size(len(data))), False

    @on(Checkbox.Changed)
    @on(TextArea.Changed)
    def changed(self, event: Message) -> None:
        event.stop()
        if isinstance(event, Checkbox.Changed):
            self.content.disabled = event.value
        self.mark_validity()
        self.post_message(self.Changed())

    def mark_validity(self) -> None:
        """Tint the content editor while its content doesn't serialize."""
        self.set_class(self.validation()[1], "-invalid")


class HeaderRow(Horizontal):
    """One editable header: a name, a UTF-8 value, and a null control.

    The inputs exist from construction, so the entry is readable even while a
    worker refreshes the Summary before the row finishes mounting.
    """

    def __init__(self, header: HeaderEntry = ("", "")) -> None:
        super().__init__(classes="header-row")
        name, value = header
        self.name_input: Input = HeaderInput(
            name, placeholder="Name", compact=True, classes="header-name column-name"
        )
        self.value_input: Input = HeaderInput(
            value or "", placeholder="Value", compact=True, classes="header-value column-value"
        )
        self.value_input.disabled = value is None
        self.null_checkbox = Checkbox(
            "",
            value is None,
            compact=True,
            tooltip="Send this header with a null value.",
            classes="header-null column-null",
        )

    def compose(self) -> ComposeResult:
        yield self.name_input
        yield self.value_input
        yield self.null_checkbox

    @property
    def entry(self) -> HeaderEntry:
        value: str | None = self.value_input.value
        if self.null_checkbox.value:
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

    @property
    def byte_size(self) -> int:
        """Bytes the headers add to the record: UTF-8 names and values."""
        return sum(
            len(name.encode("utf-8")) + (0 if value is None else len(value.encode("utf-8")))
            for name, value in self.headers
        )

    def unnamed_row(self) -> HeaderRow | None:
        """Return the first header that has a value or null but no name."""
        return next((row for row in self.rows if row.is_unnamed), None)

    def unnamed_problem(self) -> Problem | None:
        """Point at the first header that needs a name, counting from 1."""
        row = self.unnamed_row()
        return None if row is None else (f"Header {self.rows.index(row) + 1}", "Needs a name")

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
            row.value_input.disabled = event.value
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
        serializers: SerializerPool,
        field_serializers: dict[str, Serializer],
        draft: RecordDraft | None = None,
    ) -> None:
        super().__init__(id="record-composer")
        self.settings = settings
        self.service = service
        self.serializers = serializers
        self.field_serializers = field_serializers
        self.draft = draft
        self.delivery_status = ""
        self.is_producing = False
        self.is_resolving = False

    def compose(self) -> ComposeResult:
        with (
            Container(id="composer-frame", classes="kaskade-table"),
            TabbedContent(id="composer-tabs"),
        ):
            for field_name in FIELDS:
                with TabPane(field_name.title(), id=f"{field_name}-tab"):
                    yield FieldEditor(field_name, self.field_serializers[field_name])
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
                yield MetadataCell("Total Size", "", ellipsize_value=True, id="summary-total-size")
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
                if self._serialization(field_name) == Serialization.REGISTRY:
                    yield from self._compose_schema_cells(field_name)
            yield Static(Text("HEADERS", style="muted"), classes="summary-label")
            with Grid(classes="summary-grid summary-field"):
                yield MetadataCell("Count", "", ellipsize_value=True, id="summary-headers-count")
                yield MetadataCell("Size", "", ellipsize_value=True, id="summary-headers-size")
            yield Static(Text("PRODUCER", style="muted"), classes="summary-label")
            with Grid(classes="summary-grid summary-settings"):
                for label, name in CLIENT_SETTINGS:
                    yield MetadataCell(
                        label,
                        self.settings.client_setting(name),
                        ellipsize_value=True,
                        id=f"summary-{name.replace('.', '-')}",
                    )
            yield Static(id="summary-status")

    def _serialization(self, field_name: str) -> Serialization:
        if field_name == "key":
            return self.settings.key_serialization
        return self.settings.value_serialization

    def _compose_schema_cells(self, field_name: str) -> ComposeResult:
        """The registered schema's name, version, and ID, as the provider calls them."""
        provider = self.settings.registry_config.get("provider", CONFLUENT_OPTION).lower()
        if provider == APICURIO_OPTION:
            use_id = self.settings.registry_config.get(APICURIO_USE_ID, "contentId").lower()
            labels = ("Artifact", "Global ID" if use_id == "globalid" else "Content ID")
        else:
            labels = ("Subject", "Schema ID")
        name_label, id_label = labels
        with Grid(classes="summary-grid summary-schema"):
            for label, cell in ((name_label, "schema"), ("Version", "version"), (id_label, "id")):
                yield MetadataCell(
                    label, "", ellipsize_value=True, id=f"summary-{field_name}-schema-{cell}"
                )

    def on_mount(self) -> None:
        self.query_one("#record-summary").display = (
            self.app.size.width >= SUMMARY_MIN_TERMINAL_WIDTH
        )
        if self.draft is not None:
            self.call_after_refresh(self.load_draft, self.draft)
        self._update_frame()
        self.update_summary()
        if self._needs_schema():
            self.resolve_schemas()

    async def on_unmount(self) -> None:
        await self.service.aclose()
        await run_blocking(self.serializers.close)

    def _needs_schema(self) -> bool:
        return any(serializer.needs_schema for serializer in self.field_serializers.values())

    @work(group="schema-lookup", exclusive=True)
    async def resolve_schemas(self, *, produce: bool = False) -> None:
        """Look up Registry schemas off the event loop, then produce if asked to."""
        self.is_resolving = True
        try:
            for field_name in FIELDS:
                serializer = self.field_serializers[field_name]
                if serializer.needs_schema:
                    await run_blocking(serializer.resolve)
                self.editor(field_name).mark_validity()
        finally:
            self.is_resolving = False
        self.update_summary()
        self._update_frame()
        if produce:
            self.produce_draft()

    def _update_frame(self) -> None:
        self.frame.border_title = (
            rf"[{PRIMARY}]Compose Record[/] \[[{PRIMARY}]{self.settings.topic}[/]]"
        )
        parts = ["Producer Mode"]
        active_field = self.query_one(TabbedContent).active.removesuffix("-tab")
        if active_field in FIELDS:
            message, invalid = self.editor(active_field).validation()
            field_status = escape(problem_text((active_field.title(), message)))
            parts.append(f"[$text-error]{field_status}[/]" if invalid else field_status)
        elif (unnamed := self.query_one(HeadersPane).unnamed_problem()) is not None:
            parts.append(f"[$text-error]{escape(problem_text(unnamed))}[/]")
        else:
            parts.append(
                problem_text(("Headers", format_size(self.query_one(HeadersPane).byte_size)))
            )
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

    async def load_draft(self, draft: RecordDraft) -> None:
        await self.query_one(HeadersPane).load(draft.headers)
        self.editor("key").load(draft.key)
        self.editor("value").load(draft.value)
        self._update_frame()
        self.update_summary()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "produce":
            return None if self.is_producing else True
        return True

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
        headers = self.query_one(HeadersPane)
        self._summary_cell("headers-count").update_value(str(len(headers.headers)))
        self._summary_cell("headers-size").update_value(format_size(headers.byte_size))
        sizes = {field_name: self._summarize_field(field_name) for field_name in FIELDS}
        problems: list[Problem] = [
            (field_name.title(), error)
            for field_name, (_, error) in sizes.items()
            if error is not None
        ]
        total = sum(size for size, _ in sizes.values()) + headers.byte_size
        self._summary_cell("total-size").update_value("Invalid" if problems else format_size(total))
        if (unnamed := headers.unnamed_problem()) is not None:
            problems.append(unnamed)
        status = self.query_one("#summary-status", Static)
        status.set_class(bool(problems), "-invalid")
        status.update(problem_table(problems) if problems else "Ready to produce")

    def _summary_cell(self, name: str) -> MetadataCell:
        return self.query_one(f"#summary-{name}", MetadataCell)

    def _summarize_field(self, field_name: str) -> tuple[int, str | None]:
        """Show the field's serializer and size; return its byte count and any error."""
        editor = self.editor(field_name)
        self._summary_cell(f"{field_name}-serializer").update_value(editor.serializer.label)
        if self._serialization(field_name) == Serialization.REGISTRY:
            self._summarize_schema(field_name, editor.serializer)
        size = self._summary_cell(f"{field_name}-size")
        try:
            data = editor.serialize()
        except SerializationError as ex:
            size.update_value("Invalid")
            return 0, str(ex)
        size.update_value("Null" if data is None else format_size(len(data)))
        return (0 if data is None else len(data)), None

    def _summarize_schema(self, field_name: str, serializer: Serializer) -> None:
        schema = serializer.schema
        values = (
            ("…", "…", "…") if schema is None else (schema.name, schema.version, str(schema.id))
        )
        for cell, value in zip(("schema", "version", "id"), values, strict=True):
            self._summary_cell(f"{field_name}-schema-{cell}").update_value(value)

    def action_toggle_summary(self) -> None:
        summary = self.query_one("#record-summary")
        summary.display = not summary.display

    def outgoing_record(self) -> OutgoingRecord | None:
        """Serialize the draft, or reveal the first invalid field and return None."""
        headers = self.query_one(HeadersPane)
        unnamed = headers.unnamed_row()
        problem = headers.unnamed_problem()
        if unnamed is not None and problem is not None:
            self.query_one(TabbedContent).active = "headers-tab"
            unnamed.name_input.focus()
            self.notify(problem_text(problem), title="Invalid Header", severity="warning")
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
                    problem_text((field_name.title(), str(ex))),
                    title="Serialization Error",
                    severity="warning",
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
        if self._needs_schema() and not self.is_resolving:
            # Retry a failed lookup, for example after the Registry comes back.
            self.resolve_schemas(produce=True)
            return
        self.produce_draft()

    def produce_draft(self) -> None:
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
