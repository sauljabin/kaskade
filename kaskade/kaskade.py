import pkg_resources
from pyfiglet import Figlet
from rich.text import Text


class Kaskade:
    def __init__(self):
        self.name = "kaskade"
        self.version = pkg_resources.get_distribution("kaskade").version
        self.documentation = "https://github.com/sauljabin/kaskade"

    def figleted_name(self):
        figlet = Figlet(font="standard")
        return figlet.renderText(self.name).rstrip()

    def riched_name(self):
        return Text.from_markup("[magenta]{}[/]".format(self.figleted_name()))

    def riched_version(self):
        return Text.from_markup(
            "[magenta]{}[/] [green]v{}[/] [blue]{}[/]".format(
                self.name, self.version, self.documentation
            )
        )


KASKADE = Kaskade()
VERSION = KASKADE.version
NAME = KASKADE.name
DOCUMENTATION = KASKADE.documentation
