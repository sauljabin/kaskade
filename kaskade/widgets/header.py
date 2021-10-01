from kaskade.kaskade import KASKADE
from kaskade.tui_widget import TuiWidget


class Header(TuiWidget):
    name = "Header"

    def __init__(self):
        super().__init__(name=self.name)
        self.layout_size = 6

    def render(self):
        return KASKADE.riched_name()
