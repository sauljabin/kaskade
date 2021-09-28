from pyfiglet import Figlet
from rich.text import Text
from textual.widget import Widget

from kaskade import kaskade_package


class Header(Widget):
    name = "Header"

    def __init__(self):
        super().__init__(name=self.name)
        self.layout_size = 6

    def render(self):
        figlet = Figlet(font="slant")
        text = Text()
        text.append(figlet.renderText(kaskade_package.name), style="magenta")
        return text
