import re
import sys
from collections import OrderedDict
from dataclasses import dataclass
from typing import ClassVar, Generic, TypeVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Static

from kaskade import APP_NAME, APP_VERSION
from kaskade.colors import PRIMARY, SECONDARY
from kaskade.keymaps import NAVIGATION_BINDING_IDS
from kaskade.widgets import StretchyDataTable

ScreenResult = TypeVar("ScreenResult")
KASKADE_URL = "https://github.com/sauljabin/kaskade"
KASKADE_ISSUES_URL = f"{KASKADE_URL}/issues"
SELECTED_TEXT_COPY_ACTION = "screen.copy_text"
SELECTED_TEXT_COPY_SHORTCUT = "super+c" if sys.platform == "darwin" else "ctrl+shift+c"
SELECTED_TEXT_COPY_KEY_DISPLAY = "cmd+c" if sys.platform == "darwin" else "ctrl+shift+c"


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
                (
                    "Copy Selected Text"
                    if binding.action == SELECTED_TEXT_COPY_ACTION
                    else binding.description
                ),
            )
        keys = groups[group_key][1]
        for alias in _help_binding_aliases(screen, namespace, binding):
            key_display = _explicit_control_display(screen.app.get_key_display(alias))
            if key_display in keys:
                if binding.action == SELECTED_TEXT_COPY_ACTION:
                    continue
                key_display = _explicit_control_display(
                    screen.app.get_key_display(alias.with_key(alias.key, key_display=None))
                )
            if key_display not in keys:
                keys.append(key_display)

    bindings = tuple(
        HelpBinding(context, tuple(keys), description)
        for context, keys, description in groups.values()
    )
    return _focused_context(screen), bindings


def _help_binding_aliases(
    screen: Screen, namespace: object, binding: Binding
) -> tuple[Binding, ...]:
    """Return aliases normalized for Kaskade's supported Help shortcuts."""
    if binding.action == SELECTED_TEXT_COPY_ACTION:
        return (
            binding.with_key(
                SELECTED_TEXT_COPY_SHORTCUT,
                key_display=SELECTED_TEXT_COPY_KEY_DISPLAY,
            ),
        )
    return _binding_aliases(screen, namespace, binding)


def _explicit_control_display(key_display: str) -> str:
    """Render caret-style control chords with an explicit ctrl+ prefix."""
    return f"ctrl+{key_display[1:]}" if key_display.startswith("^") else key_display


def _binding_aliases(screen: Screen, namespace: object, binding: Binding) -> tuple[Binding, ...]:
    """Return every effective alias owned by the binding's namespace."""
    aliases = tuple(
        candidate
        for active_namespace, candidate, enabled, _ in screen.active_bindings.values()
        if enabled
        and active_namespace is namespace
        and not candidate.system
        and candidate.action == binding.action
        and candidate.id == binding.id
    )
    return aliases or (binding,)


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

    BINDING_GROUP_TITLE = "Help"
    AUTO_FOCUS = "#help-table"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            "escape",
            "close",
            "Back",
            key_display="esc",
            tooltip="Return to the previous Kaskade screen.",
            id="kaskade.help.close",
        ),
        Binding(
            "q,?,f1",
            "close",
            "Back",
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
        dialog = Vertical(id="help-dialog")
        dialog.border_title = f"[{PRIMARY}]Help[/] — {self.context}"
        with dialog:
            yield Static(
                f"[b {PRIMARY}]{APP_NAME.title()}[/] " f"[b {SECONDARY}]v{APP_VERSION}[/]",
                id="help-heading",
            )
            yield Static(
                "[b]About Kaskade[/] — A terminal user interface for Apache Kafka.\n"
                f'Project: [link="{KASKADE_URL}"]{KASKADE_URL}[/link]\n'
                "Report Issues: "
                f'[link="{KASKADE_ISSUES_URL}"]{KASKADE_ISSUES_URL}[/link]',
                id="help-about",
            )
            table: StretchyDataTable[str] = StretchyDataTable(
                id="help-table",
                cursor_type="row",
                zebra_stripes=True,
            )
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
        yield Footer(compact=True)

    def action_close(self) -> None:
        self.dismiss()


class HelpableModalScreen(ModalScreen[ScreenResult], Generic[ScreenResult]):
    """A Kaskade modal that can open contextual help without capturing text."""

    BINDINGS: ClassVar[list[BindingType]] = []


HELP_BINDING = Binding(
    "?,f1",
    "app.toggle_help",
    "Help",
    key_display="?",
    tooltip="Show all shortcuts available in the current context.",
    id="help.toggle",
)


def modal_bindings(*bindings: BindingType) -> list[BindingType]:
    """Place contextual modal commands before the shared Help command."""
    return [*bindings, HELP_BINDING]
