"""Record filter and chunk size screens."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container
from textual.widgets import Footer, Input, OptionList
from textual.widgets.option_list import Option

from kaskade.colors import PRIMARY
from kaskade.commands import RecordFilters
from kaskade.help import HelpableModalScreen, modal_bindings
from kaskade.widgets import KaskadeOptionList

SUBMIT_SHORTCUT = "enter"
BACK_SHORTCUT = "escape"


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
