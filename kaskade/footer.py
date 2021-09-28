from rich.text import Text
from textual.widget import Widget

from kaskade import kaskade_package


class Footer(Widget):
    name = "Footer"

    def __init__(self):
        super().__init__(name=self.name)
        self.layout_size = 1

    def render(self):
        text = Text(justify="right")
        text.append(kaskade_package.name, style="bold magenta")
        text.append(" v{}".format(kaskade_package.version), style="green")
        return text
