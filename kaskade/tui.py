from textual.app import App
from textual.widgets import Placeholder


class Kaskade(App):
    def __init__(self):
        super().__init__(title="kaskade")

    def init(self):
        pass


class Sidebar(Placeholder):
    pass
