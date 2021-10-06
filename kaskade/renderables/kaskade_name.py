from pyfiglet import Figlet
from rich.text import Text

from kaskade import NAME


class KaskadeName:
    def __str__(self):
        figlet = Figlet(font="standard")
        return figlet.renderText(NAME).rstrip()

    def __rich__(self):
        return Text.from_markup("[magenta]{}[/]".format(self))


if __name__ == "__main__":
    from rich.console import Console

    console = Console()
    console.print(KaskadeName())
