from rich.panel import Panel
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade import styles
from kaskade.renderables.shortcuts import Shortcuts


class Help(Widget):
    has_focus = Reactive(False)

    def on_focus(self) -> None:
        self.has_focus = True

    async def on_blur(self) -> None:
        self.has_focus = False
        self.app.show_help = False

    def render(self) -> Panel:
        return Panel(
            Shortcuts(),
            title="Help",
            border_style=styles.BORDER_FOCUSED,
            box=styles.BOX,
            title_align="left",
            padding=0,
        )
