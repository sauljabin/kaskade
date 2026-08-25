from rich.theme import Theme as RichTheme
from textual.app import App
from textual.theme import BUILTIN_THEMES, Theme, ThemeProvider

DEFAULT_THEME = "eva01"

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

    COMMANDS = App.COMMANDS | {ThemeProvider}

    def __init__(self) -> None:
        self._rich_theme_pushed = False
        super().__init__()
        self.register_theme(EVA01_THEME)
        self.theme = DEFAULT_THEME
        self._sync_rich_theme()

    def watch_theme(self, _: str) -> None:
        self._sync_rich_theme()

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
