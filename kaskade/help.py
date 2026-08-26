import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import ClassVar, Generic, TypeVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Static

from kaskade.keymaps import NAVIGATION_BINDING_IDS
from kaskade.widgets import StretchyDataTable

ScreenResult = TypeVar("ScreenResult")


@dataclass(frozen=True)
class HelpBinding:
    """A configured binding rendered in the contextual help window."""

    context: str
    keys: tuple[str, ...]
    description: str


def contextual_help(screen: Screen) -> tuple[str, tuple[HelpBinding, ...]]:
    """Snapshot the effective bindings before the help modal takes focus."""
    groups: OrderedDict[tuple[int, str], tuple[str, list[str], str]] = OrderedDict()

    for namespace, binding, enabled, _ in screen.active_bindings.values():
        if not enabled or binding.system or not binding.description:
            continue

        group_key = (id(namespace), binding.action)
        if group_key not in groups:
            groups[group_key] = (
                (
                    "Navigation"
                    if binding.id in NAVIGATION_BINDING_IDS
                    else _binding_context(namespace)
                ),
                [],
                binding.description,
            )
        keys = groups[group_key][1]
        key_display = screen.app.get_key_display(binding)
        if key_display not in keys:
            keys.append(key_display)

    bindings = tuple(
        HelpBinding(context, tuple(keys), description)
        for context, keys, description in groups.values()
    )
    return _focused_context(screen), bindings


def _binding_context(namespace: object) -> str:
    title = getattr(namespace, "BINDING_GROUP_TITLE", None)
    return str(title) if title else _class_title(namespace)


def _focused_context(screen: Screen) -> str:
    if title := getattr(screen, "BINDING_GROUP_TITLE", None):
        return str(title)
    if screen.focused is not None:
        for node in screen.focused.ancestors_with_self:
            if title := getattr(node, "BINDING_GROUP_TITLE", None):
                return str(title)
    return "Application"


def _class_title(value: object) -> str:
    name = value.__class__.__name__.removeprefix("Kaskade")
    return re.sub(r"(?<!^)(?=[A-Z])", " ", name).removesuffix(" Screen")


class HelpScreen(ModalScreen[None]):
    """A centered, keyboard-navigable window of contextual shortcuts."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }

    HelpScreen > #help-dialog {
        border: $secondary;
        width: 80%;
        max-width: 110;
        height: 80%;
        background: $surface;
        padding: 0 1;
    }

    HelpScreen #help-table {
        border: none;
        width: 100%;
        height: 1fr;
    }

    HelpScreen #help-footer {
        width: 100%;
        height: 1;
        content-align: center middle;
        color: $text-muted;
    }

    HelpScreen.-narrow > #help-dialog {
        width: 100%;
        max-width: 100%;
        height: 100%;
    }
    """

    BINDING_GROUP_TITLE = "Help"
    AUTO_FOCUS = "#help-table"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            "escape,q",
            "close",
            "Close Help",
            show=False,
            tooltip="Return to the previous Kaskade screen.",
            id="kaskade.help.close",
        ),
        Binding(
            "?,f1",
            "close",
            "Close Help",
            show=False,
            tooltip="Toggle the contextual help window.",
            id="help.toggle",
        ),
    ]

    def __init__(self, context: str, bindings: tuple[HelpBinding, ...]) -> None:
        super().__init__()
        self.context = context
        self.help_bindings = bindings

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            table: StretchyDataTable[str] = StretchyDataTable(
                id="help-table",
                cursor_type="row",
                zebra_stripes=True,
            )
            table.border_title = f"[primary]Kaskade Help[/] — {self.context}"
            table.add_column("Context", width=12, stretch=1)
            table.add_column("Key", width=14, stretch=1)
            table.add_column("Action", width=20, stretch=3)
            for binding in self.help_bindings:
                table.add_row(
                    binding.context,
                    " / ".join(binding.keys),
                    binding.description,
                )
            yield table
            yield Static(
                "[b]j/k[/], arrows, Page Up/Down, [b]g/G[/] navigate"
                "  •  [b]Esc/q/?/F1[/] closes",
                id="help-footer",
            )

    def action_close(self) -> None:
        self.dismiss()


class HelpableModalScreen(ModalScreen[ScreenResult], Generic[ScreenResult]):
    """A Kaskade modal that can open contextual help without capturing text."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            "?,f1",
            "app.toggle_help",
            "Help",
            key_display="?",
            tooltip="Show all shortcuts available in the current context.",
            id="help.toggle",
        )
    ]
