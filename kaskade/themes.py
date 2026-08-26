from collections.abc import Iterable
from functools import partial
from typing import ClassVar

from rich.theme import Theme as RichTheme
from textual.app import App, SystemCommand
from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.theme import BUILTIN_THEMES, Theme
from textual.widgets import HelpPanel

DEFAULT_THEME = "eva01"
KASKADE_COMMAND_ID_PREFIX = "kaskade."

EVA01_THEME = Theme(
    name=DEFAULT_THEME,
    primary="#9B4DCA",
    secondary="#A6FF4D",
    warning="#FF9D1C",
    error="#FF4D5A",
    success="#A6FF4D",
    accent="#FF7A00",
    foreground="#F3ECFF",
    background="#100A1C",
    surface="#1C1030",
    panel="#2A1845",
    boost="#341B55",
    dark=True,
)


def available_theme_names() -> tuple[str, ...]:
    """Return every Textual built-in theme plus Kaskade's default theme."""
    return tuple(sorted((*BUILTIN_THEMES, EVA01_THEME.name)))


def _rich_color(color: str) -> str:
    """Translate Textual ANSI color tokens into Rich color names."""
    return color.removeprefix("ansi_")


class KaskadeApp(App):
    """Base application with Textual and Rich theme support."""

    TITLE = "Kaskade"
    BINDING_GROUP_TITLE = "Application"
    HORIZONTAL_BREAKPOINTS = [  # noqa: RUF012
        (0, "-narrow"),
        (80, "-wide"),
    ]
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            "f1",
            "toggle_help",
            "Help",
            tooltip="Show all shortcuts available in the current context.",
            id="help.toggle",
        ),
        Binding(
            "ctrl+q",
            "quit",
            "Quit",
            priority=True,
            tooltip="Quit Kaskade and return to the command prompt.",
            id="app.quit",
        ),
        Binding(
            "ctrl+p",
            "command_palette",
            "Palette",
            show=False,
            priority=True,
            tooltip="Search available Kaskade and Textual commands.",
            id="app.command-palette",
        ),
    ]

    def __init__(self) -> None:
        self._rich_theme_pushed = False
        super().__init__()
        self.register_theme(EVA01_THEME)
        self.theme = DEFAULT_THEME
        self._sync_rich_theme()

    def watch_theme(self, _: str) -> None:
        self._sync_rich_theme()

    def action_toggle_help(self) -> None:
        """Show or hide Textual's contextual help panel."""
        if self.screen.query(HelpPanel):
            self.action_hide_help_panel()
        else:
            self.action_show_help_panel()

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        """Add active Kaskade bindings to Textual's command palette."""
        yield from super().get_system_commands(screen)

        command_ids: set[str] = set()
        for namespace, binding, enabled, _ in screen.active_bindings.values():
            if (
                not enabled
                or binding.id is None
                or not binding.id.startswith(KASKADE_COMMAND_ID_PREFIX)
                or binding.id in command_ids
            ):
                continue

            command_ids.add(binding.id)
            yield SystemCommand(
                binding.description,
                binding.tooltip or f"Run {binding.description.lower()}.",
                partial(self.run_action, binding.action, default_namespace=namespace),
            )

    def _sync_rich_theme(self) -> None:
        """Expose the active Textual colors to Rich renderables by semantic name."""
        if not hasattr(self, "console"):
            return

        if self._rich_theme_pushed:
            self.console.pop_theme()

        theme = self.current_theme
        styles = {
            "primary": _rich_color(theme.primary),
            "secondary": _rich_color(theme.secondary or theme.primary),
            "warning": _rich_color(theme.warning or theme.primary),
            "error": _rich_color(theme.error or theme.primary),
            "success": _rich_color(theme.success or theme.primary),
            "accent": _rich_color(theme.accent or theme.primary),
            "repr.str": _rich_color(theme.primary),
        }
        self.console.push_theme(RichTheme(styles))
        self._rich_theme_pushed = True
