from textual.widget import Widget

from kaskade.kaskade import kaskade


class Header(Widget):
    name = "Header"

    def __init__(self):
        super().__init__(name=self.name)
        self.layout_size = 6

    def render(self):
        return kaskade.riched_name()
