"""The header editor opened from the composer's Headers tab."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container
from textual.widgets import Checkbox, Footer, Input

from kaskade.colors import PRIMARY
from kaskade.help import HelpableModalScreen, modal_bindings

SAVE_SHORTCUT = "ctrl+s,ctrl+shift+s,f2"
BACK_SHORTCUT = "escape"

HeaderEntry = tuple[str, str | None]


class HeaderScreen(HelpableModalScreen[HeaderEntry]):
    """Add or edit one header; its value is a UTF-8 string or null."""

    BINDING_GROUP_TITLE = "Header"
    AUTO_FOCUS = "#header-name"
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            SAVE_SHORTCUT,
            "save",
            "Save Header",
            tooltip="Keep this header in the record draft.",
            id="kaskade.header.save",
        ),
        Binding(
            BACK_SHORTCUT,
            "back",
            "Back",
            key_display="esc",
            tooltip="Close the header editor without changes.",
            id="kaskade.header.close",
        ),
    )

    def __init__(self, header: HeaderEntry | None = None) -> None:
        super().__init__()
        self.header = header

    def compose(self) -> ComposeResult:
        name, value = self.header or ("", "")
        form = Container(classes="header-form")
        form.border_title = f"[{PRIMARY}]{'Edit' if self.header else 'Add'} Header[/]"
        with form:
            name_input = Input(name, id="header-name", classes="kaskade-input")
            name_input.border_title = "Name"
            yield name_input
            value_input = Input(value or "", id="header-value", classes="kaskade-input")
            value_input.border_title = "Value"
            value_input.disabled = value is None
            yield value_input
            yield Checkbox("Null Value", value is None, id="header-null")
        yield Footer(compact=True)

    @on(Checkbox.Changed, "#header-null")
    def toggle_null(self, event: Checkbox.Changed) -> None:
        self.query_one("#header-value", Input).disabled = event.value

    def action_save(self) -> None:
        name_input = self.query_one("#header-name", Input)
        if not name_input.value:
            name_input.focus()
            self.notify("Header names can't be empty", title="Invalid Header", severity="warning")
            return
        value: str | None = self.query_one("#header-value", Input).value
        if self.query_one("#header-null", Checkbox).value:
            value = None
        self.dismiss((name_input.value, value))

    def action_back(self) -> None:
        self.dismiss()
