from rich.console import RenderableType
from rich.text import Text

from kaskade import NAME, VERSION


class KaskadeVersion:
    def __str__(self) -> str:
        return "{} v{}".format(NAME, VERSION)

    def __rich__(self) -> RenderableType:
        return Text.from_markup("[magenta]{}[/] [green]v{}[/]".format(NAME, VERSION))
