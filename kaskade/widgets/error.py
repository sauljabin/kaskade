from rich.panel import Panel
from rich.text import Text
from textual.widget import Widget

from kaskade import styles
from kaskade.emojis import FIRE


class Error(Widget):
    message = ""

    async def on_blur(self) -> None:
        self.app.error = ""
        self.message = ""

    def render(self) -> Panel:
        text = Text.from_markup("{}".format(self.message))
        return Panel(
            text,
            title="{} [bold]error[/]".format(FIRE),
            border_style=styles.BORDER_ERROR,
            box=styles.BOX,
            title_align="left",
        )
