from kaskade.kaskade import kaskade
from kaskade.tui_widget import TuiWidget


class Footer(TuiWidget):
    name = "Footer"

    def __init__(self):
        super().__init__(name=self.name)
        self.layout_size = 1

    def render(self):
        return kaskade.riched_version()
