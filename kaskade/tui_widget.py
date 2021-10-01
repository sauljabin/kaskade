from rich import box
from rich.panel import Panel
from rich.text import Text
from textual.reactive import Reactive
from textual.widget import Widget


class TuiWidget(Widget):
    mouse_over = Reactive(False)
    has_focus = Reactive(False)

    def __init__(self, name):
        super().__init__(name=name)
        self.title = name

    def on_mount(self):
        self.set_interval(0.1, self.refresh)
        self.initial_state()

    def render(self):
        return Panel(
            self.render_content(),
            title=self.title,
            border_style=self.border_style(),
            box=box.SQUARE,
            title_align="left",
        )

    def border_style(self):
        if self.has_focus:
            return "green"
        elif self.mouse_over:
            return "grey100"
        else:
            return "grey82"

    def render_content(self):
        return Text()

    def on_enter(self):
        self.mouse_over = True

    def on_leave(self):
        self.mouse_over = False

    def on_focus(self):
        self.has_focus = True

    def on_blur(self):
        self.has_focus = False

    def on_key_press(self, key):
        pass

    def initial_state(self):
        pass
