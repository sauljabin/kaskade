from pyfiglet import Figlet
from rich.console import RenderableType
from rich.text import Text

from kaskade import NAME


class KaskadeName:
    def __str__(self) -> str:
        figlet = Figlet(font="standard")
        figlet_string = figlet.renderText(NAME).rstrip()
        return figlet_string if figlet_string else NAME

    def __rich__(self) -> RenderableType:
        return Text.from_markup("[magenta]{}[/]".format(self))


if __name__ == "__main__":
    from rich.console import Console, RenderableType

    console = Console()
    console.print(KaskadeName())
