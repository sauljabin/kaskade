from pyfiglet import Figlet
from rich.text import Text

from kaskade import APP_NAME, APP_VERSION


class KaskadeName:
    def __str__(self) -> str:
        figlet = Figlet(font="standard")
        figlet_string: str = figlet.renderText(APP_NAME).rstrip()
        return figlet_string

    def __rich__(self) -> Text:
        return Text.from_markup(
            "[magenta]{}[/]\n[green bold]v{}[/]".format(self, APP_VERSION)
        )
