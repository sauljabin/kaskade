from rich.text import Text

from kaskade import APP_NAME, APP_VERSION


class KaskadeVersion:
    def __str__(self) -> str:
        return "{} v{}".format(APP_NAME, APP_VERSION)

    def __rich__(self) -> Text:
        return Text.from_markup(
            "[magenta]{}[/] [green]v{}[/]".format(APP_NAME, APP_VERSION)
        )
