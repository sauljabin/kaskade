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

from kaskade.help import (
    HELP_BINDING,
    SELECTED_TEXT_COPY_KEY_DISPLAY,
    SELECTED_TEXT_COPY_SHORTCUT,
    HelpScreen,
    contextual_help,
)
from kaskade.keymaps import NAVIGATION_BINDING_IDS
from kaskade.settings import AppSettings, load_settings
from kaskade.themes import KASKADE_THEMES, parse_custom_themes, resolve_theme

KASKADE_COMMAND_ID_PREFIX = "kaskade."


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

    def __init__(self, *, settings: AppSettings | None = None) -> None:
        """Use settings the CLI already resolved, or load settings.yaml."""
        self._rich_theme_pushed = False
        # Textual resolves a relative CSS_PATH against the subclass's module, so
        # anchor it here for apps defined in other packages.
        css_path = self.CSS_PATH
        super().__init__(
            css_path=Path(__file__).parent / css_path if isinstance(css_path, str) else css_path
        )
        settings = load_settings() if settings is None else settings
        custom_themes, custom_theme_warnings = parse_custom_themes(settings.custom_themes)
        for theme in (*KASKADE_THEMES, *custom_themes):
            self.register_theme(theme)
        self.settings = resolve_theme(
            replace(settings, warnings=(*settings.warnings, *custom_theme_warnings)),
            self.available_themes,
        )
        self.set_keymap(self.settings.keymap)
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
        # Omitted colors follow Textual's own fallbacks.
        primary = _rich_color(theme.primary)
        secondary = _rich_color(theme.secondary or theme.primary)
        warning = _rich_color(theme.warning or theme.primary)
        error = _rich_color(theme.error) if theme.error else secondary
        success = _rich_color(theme.success) if theme.success else secondary
        styles = {
            "primary": primary,
            "secondary": secondary,
            "warning": warning,
            "text-warning": _rich_color(self.get_css_variables()["text-warning"]),
            "foreground": _rich_color(self.get_css_variables()["foreground"]),
            "muted": f"dim {_rich_color(theme.foreground or theme.primary)}",
            "error": error,
            "success": success,
            "accent": _rich_color(theme.accent or theme.primary),
            "repr.str": primary,
            "json.key": f"bold {primary}",
            "json.str": primary,
            "json.number": secondary,
            "json.bool_true": success,
            "json.bool_false": error,
            "json.null": warning,
        }
        self.console.push_theme(RichTheme(styles))
        self._rich_theme_pushed = True
