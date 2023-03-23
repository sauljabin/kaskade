from pyfiglet import Figlet
from rich.text import Text

from kaskade import APP_NAME, APP_VERSION
from kaskade.styles.colors import PRIMARY, SECONDARY


class KaskadeName:
    def __init__(self, include_version: bool = True):
        self.include_version = include_version

    def __str__(self) -> str:
        figlet = Figlet(font="standard")
        figlet_string: str = figlet.renderText(APP_NAME).rstrip()
        return figlet_string

    def __rich__(self) -> Text:
        text = Text(str(self), style=f"{PRIMARY} bold")

        if self.include_version:
            text.append(f"v{APP_VERSION}", style=f"{SECONDARY} bold")

        return text
