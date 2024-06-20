from pyfiglet import Figlet
from rich.text import Text

from kaskade import APP_NAME, APP_VERSION
from kaskade.styles.colors import PRIMARY, SECONDARY


class KaskadeName:
    def __init__(self, include_version: bool = False, include_slogan: bool = False):
        self.include_slogan = include_slogan
        self.include_version = include_version

    def __str__(self) -> str:
        figlet = Figlet(font="standard")
        figlet_string: str = figlet.renderText(APP_NAME).rstrip()
        return figlet_string

    def __rich__(self) -> Text:
        text = Text(str(self), style=f"{PRIMARY} bold")

        if self.include_version:
            text.append(f"\nv{APP_VERSION}", style=f"{SECONDARY}")

        if self.include_slogan:
            text.append("\na kafka text user interface", style=f"{SECONDARY}")

        return text
