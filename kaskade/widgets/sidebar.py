from rich.panel import Panel
from rich.text import Text
from textual.keys import Keys
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade import styles
from kaskade.renderables.scrollable_list import ScrollableList


class Sidebar(Widget):
    has_focus = Reactive(False)
    scrollable_list = None

    def on_mount(self):
        self.set_interval(0.1, self.refresh)
        self.scrollable_list = ScrollableList(
            self.app.topics, max_len=self.size.height - 2
        )

    def on_focus(self):
        self.has_focus = True

    def on_blur(self):
        self.has_focus = False

    def on_resize(self):
        self.scrollable_list = ScrollableList(
            self.app.topics,
            max_len=self.size.height - 2,
            pointer=self.scrollable_list.pointer,
        )

    def render(self):
        title = Text.from_markup(
            "Topics ([blue]total:[/] [yellow]{}[/])".format(len(self.app.topics))
        )
        return Panel(
            self.scrollable_list,
            title=title,
            border_style=styles.BORDER_FOCUSED if self.has_focus else styles.BORDER,
            box=styles.BOX,
            title_align="left",
        )

    def on_key(self, event):
        if event.key == Keys.Up:
            self.scrollable_list.previous()
        elif event.key == Keys.Down:
            self.scrollable_list.next()

        self.app.topic = self.scrollable_list.selected
