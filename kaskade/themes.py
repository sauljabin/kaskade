import sys
from collections.abc import Iterable
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import ClassVar

from rich.theme import Theme as RichTheme
from textual import events, on
from textual.app import App, SystemCommand
from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.theme import BUILTIN_THEMES, Theme

from kaskade.help import (
    HELP_BINDING,
    SELECTED_TEXT_COPY_KEY_DISPLAY,
    SELECTED_TEXT_COPY_SHORTCUT,
    HelpScreen,
    contextual_help,
)
from kaskade.keymaps import NAVIGATION_BINDING_IDS
from kaskade.settings import AppSettings, load_settings

DEFAULT_THEME = "eva01-berserk"
KASKADE_COMMAND_ID_PREFIX = "kaskade."
EVA01_THEME = Theme(
    name="eva01",
    primary="#9B4DCA",
    secondary="#A6FF4D",
    warning="#FF9D1C",
    error="#FF4D5A",
    success="#A6FF4D",
    accent="#FF7A00",
    foreground="#F3ECFF",
    background="#2A1845",
    surface="#1F0E36",
    panel="#0E0024",
    boost="#341B55",
    dark=True,
)
EVA01_BERSERK_THEME = Theme(
    name=DEFAULT_THEME,
    primary="#9B4DCA",
    secondary="#A6FF4D",
    warning="#FF9D1C",
    error="#FF4D5A",
    success="#A6FF4D",
    accent="#FF7A00",
    foreground="#F3ECFF",
    background="#0E0024",
    surface="#1C1030",
    panel="#2A1845",
    boost="#341B55",
    dark=True,
)
KASKADE_THEMES = (EVA01_THEME, EVA01_BERSERK_THEME)


def available_theme_names() -> tuple[str, ...]:
    """Return every Textual built-in theme plus Kaskade's custom themes."""
    return tuple(sorted((*BUILTIN_THEMES, *(theme.name for theme in KASKADE_THEMES))))


def _resolve_theme(settings: AppSettings) -> AppSettings:
    configured_theme = settings.theme
    if configured_theme is None:
        return replace(settings, theme=DEFAULT_THEME)
    if configured_theme not in available_theme_names():
        return replace(
            settings,
            theme=DEFAULT_THEME,
            warnings=(*settings.warnings, f"Ignoring 'theme': unknown theme {configured_theme!r}"),
        )
    return settings


def _rich_color(color: str) -> str:
    """Translate Textual ANSI color tokens into Rich color names."""
    return color.removeprefix("ansi_")


class KaskadeApp(App, inherit_bindings=False):
    """Base application with Textual and Rich theme support."""

    TITLE = "Kaskade"
    CSS_PATH = "styles.css"
    BINDING_GROUP_TITLE = "Application"
    COMMAND_PALETTE_BINDING = "colon"
    HORIZONTAL_BREAKPOINTS = [  # noqa: RUF012
        (0, "-narrow"),
        (80, "-wide"),
    ]
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            "ctrl+c",
            "quit",
            "Quit",
            priority=True,
            tooltip="Quit Kaskade and return to the command prompt.",
            id="app.quit",
        ),
        Binding(
            SELECTED_TEXT_COPY_SHORTCUT,
            "screen.copy_text",
            "Copy Selected Text",
            key_display=SELECTED_TEXT_COPY_KEY_DISPLAY,
            show=False,
            priority=True,
            tooltip="Copy only the text selected on the current screen.",
        ),
        *(
            [
                Binding(
                    "super+c",
                    "ignore_selected_text_copy",
                    "Copy Selected Text",
                    show=False,
                    priority=True,
                    system=True,
                    tooltip="Use Ctrl+Shift+C to copy selected text on Linux.",
                )
            ]
            if sys.platform != "darwin"
            else []
        ),
        Binding(
            "?,f1",
            "toggle_help",
            "Help",
            key_display="?",
            tooltip="Show all shortcuts available in the current context.",
            id="help.toggle",
        ),
        Binding(
            ":,ctrl+p",
            "command_palette",
            "Commands",
            key_display=":",
            show=False,
            tooltip="Search available Kaskade and Textual commands.",
            id="app.command-palette",
        ),
    ]

    def __init__(self, *, settings_path: Path | None = None) -> None:
        self._rich_theme_pushed = False
        super().__init__()
        self.settings = _resolve_theme(load_settings(settings_path))
        self.set_keymap(self.settings.keymap)
        for theme in KASKADE_THEMES:
            self.register_theme(theme)
        assert self.settings.theme is not None
        self.theme = self.settings.theme
        self._sync_rich_theme()

    def on_mount(self) -> None:
        self.screen.add_class("main-view-screen")
        for warning_message in self.settings.warnings:
            self.notify(
                warning_message,
                title="Settings Configuration",
                severity="warning",
            )

    def watch_theme(self, _: str) -> None:
        self._sync_rich_theme()

    def action_toggle_help(self) -> None:
        """Open a contextual help window above the current screen."""
        context, bindings = contextual_help(self.screen)
        self.push_screen(HelpScreen(context, bindings))

    def action_ignore_selected_text_copy(self) -> None:
        """Shadow Textual's macOS copy alias on non-macOS platforms."""

    @on(events.DeliveryComplete)
    def on_record_delivery_complete(self, event: events.DeliveryComplete) -> None:
        """Notify the user after a record export is delivered."""
        if event.name != "record":
            return
        if event.path is None:
            self.notify("Saved record", title="Record Export")
        else:
            self.notify(
                f"Saved record to [$text-success]{str(event.path)!r}",
                title="Record Export",
            )

    @on(events.DeliveryFailed)
    def on_record_delivery_failed(self, event: events.DeliveryFailed) -> None:
        """Notify the user when a record export cannot be delivered."""
        if event.name == "record":
            self.notify(
                "Failed to save record",
                title="Record Export",
                severity="error",
            )

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        """Add active Kaskade bindings to Textual's command palette."""
        widget_size_actions = (screen.action_maximize, screen.action_minimize)
        help_panel_actions = (self.action_show_help_panel, self.action_hide_help_panel)
        for command in super().get_system_commands(screen):
            if command.callback in help_panel_actions:
                yield SystemCommand(
                    HELP_BINDING.description,
                    HELP_BINDING.tooltip,
                    self.action_toggle_help,
                )
            elif command.callback not in widget_size_actions:
                yield command

        command_ids: set[str] = set()
        for namespace, binding, enabled, _ in screen.active_bindings.values():
            if (
                not enabled
                or binding.id is None
                or not binding.id.startswith(KASKADE_COMMAND_ID_PREFIX)
                or binding.id in NAVIGATION_BINDING_IDS
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
            "text-warning": _rich_color(self.get_css_variables()["text-warning"]),
            "muted": f"dim {_rich_color(theme.foreground or theme.primary)}",
            "error": _rich_color(theme.error or theme.primary),
            "success": _rich_color(theme.success or theme.primary),
            "accent": _rich_color(theme.accent or theme.primary),
            "repr.str": _rich_color(theme.primary),
            "json.key": f"bold {_rich_color(theme.primary)}",
            "json.str": _rich_color(theme.primary),
            "json.number": _rich_color(theme.secondary or theme.primary),
            "json.bool_true": _rich_color(theme.success or theme.primary),
            "json.bool_false": _rich_color(theme.error or theme.primary),
            "json.null": _rich_color(theme.warning or theme.primary),
        }
        self.console.push_theme(RichTheme(styles))
        self._rich_theme_pushed = True
