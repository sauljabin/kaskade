from rich.panel import Panel
from rich.text import Text
from textual.keys import Keys
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade import styles


class Sidebar(Widget):
    focused_topic_index = -1
    topics = []
    has_focus = Reactive(False)

    def on_mount(self):
        self.set_interval(0.1, self.refresh)
        self.initial_state()

    def on_focus(self):
        self.has_focus = True

    def on_blur(self):
        self.has_focus = False

    def render(self):
        title = Text.from_markup(
            "Topics ([blue]total:[/] [yellow]{}[/])".format(len(self.topics))
        )
        return Panel(
            self.render_content(),
            title=title,
            border_style=styles.BORDER_FOCUSED if self.has_focus else styles.BORDER,
            box=styles.BOX,
            title_align="left",
        )

    def initial_state(self):
        self.focused_topic_index = -1
        self.has_focus = False

    def render_content(self):
        content = Text(overflow="ellipsis")
        for index, topic in enumerate(self.topics):
            if self.focused_topic_index == index:
                content.append("\u25B6", "green bold")
                content.append(topic.name, "green bold")
            else:
                content.append(" ")
                content.append(topic.name)
            content.append("\n")

        return content

    def on_key_press(self, key):
        if key == Keys.Up:
            self.focused_topic_index -= 1
            if self.focused_topic_index < 0:
                self.focused_topic_index = len(self.topics) - 1
        elif key == Keys.Down:
            self.focused_topic_index += 1
            if self.focused_topic_index >= len(self.topics):
                self.focused_topic_index = 0

        self.app.topic = self.topics[self.focused_topic_index]
