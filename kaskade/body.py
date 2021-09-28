from rich import box
from rich.panel import Panel
from textual.reactive import Reactive
from textual.widget import Widget


class Data(Widget):
    mouse_over = Reactive(False)
    has_focus = Reactive(False)
    name = "Data"

    def __init__(self):
        super().__init__(name=self.name)

    def render(self):
        return Panel(
            "Hello World!",
            title=self.name,
            border_style=self.border_style(),
            box=box.SQUARE,
            title_align="left",
        )

    def border_style(self):
        return "green" if self.mouse_over or self.has_focus else "grey93"

    async def on_enter(self):
        self.mouse_over = True

    async def on_leave(self):
        self.mouse_over = False

    async def on_focus(self, event):
        self.has_focus = True

    async def on_blur(self, event):
        self.has_focus = False
