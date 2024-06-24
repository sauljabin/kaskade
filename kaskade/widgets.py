from pyfiglet import Figlet
from rich.console import Group
from rich.text import Text
from textual.widget import Widget

from kaskade import APP_NAME, APP_VERSION, APP_NAME_SHORT
from kaskade.colors import PRIMARY, SECONDARY


class KaskadeBanner(Widget):
    def __init__(
        self, *, include_version: bool = False, include_slogan: bool = False, short: bool = False
    ):
        super().__init__()
        self.include_slogan = include_slogan
        self.include_version = include_version
        self.short = short

    def render(self) -> Group:
        figlet = Figlet(font="standard")
        kaskade_name = Text(
            figlet.renderText(APP_NAME_SHORT if self.short else APP_NAME).rstrip(),
            style=f"{PRIMARY} bold",
        )
        version_text = Text("", justify="right")

        if self.include_slogan:
            version_text.append("a kafka text user interface ", style=f"{SECONDARY}")

        if self.include_version:
            version_text.append(f"v{APP_VERSION} ", style=f"{SECONDARY}")

        return Group(kaskade_name, version_text)
