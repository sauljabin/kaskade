from rich.panel import Panel
from textual.widget import Widget

from kaskade import styles
from kaskade.emojis import INFO
from kaskade.renderables.shortcuts import Shortcuts


class Help(Widget):
    async def on_blur(self) -> None:
        self.app.show_help = False

    def render(self) -> Panel:
        return Panel(
            Shortcuts(),
            title="{} help".format(INFO),
            border_style=styles.BORDER_FOCUSED,
            box=styles.BOX,
            title_align="left",
            padding=0,
        )
