from textual.widget import Widget

from kaskade.kaskade import kaskade


class Footer(Widget):
    name = "Footer"

    def __init__(self):
        super().__init__(name=self.name)
        self.layout_size = 1

    def render(self):
        return kaskade.riched_version()
