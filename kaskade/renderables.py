from pyfiglet import Figlet
from rich.table import Table
from rich.text import Text
from textual.keys import Keys

from kaskade import APP_NAME, APP_VERSION
from kaskade.colors import PRIMARY, SECONDARY
from kaskade.unicodes import LEFT, RIGHT, UP, DOWN


class KaskadeName:
    def __init__(self, include_version: bool = False, include_slogan: bool = False):
        self.include_slogan = include_slogan
        self.include_version = include_version

    def __rich__(self) -> Text:
        figlet = Figlet(font="standard")
        text = Text(figlet.renderText(APP_NAME).rstrip(), style=f"{PRIMARY} bold")

        if self.include_version:
            text.append(f"\nv{APP_VERSION}", style=f"{SECONDARY}")

        if self.include_slogan:
            text.append("\na kafka text user interface", style=f"{SECONDARY}")

        return text


class KaskadeInfo:

    def __rich__(self) -> Table:
        table = Table(box=None, show_header=False)
        table.add_column(style=f"bold {SECONDARY}")
        table.add_column()

        table.add_row("navigate:", f"{LEFT} {RIGHT} {UP} {DOWN}")
        table.add_row("help:", "?")
        table.add_row("quit:", Keys.ControlC)

        return table
