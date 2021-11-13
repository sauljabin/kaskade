from rich.panel import Panel
from textual.widget import Widget

from kaskade import styles
from kaskade.emojis import INFO
from kaskade.renderables.shortcuts import Shortcuts


class Help(Widget):
    def render(self) -> Panel:
        return Panel(
            Shortcuts(),
            title="{} [bold]help[/]".format(INFO),
            border_style=styles.BORDER_FOCUSED,
            box=styles.BOX,
            title_align="left",
            padding=0,
        )
