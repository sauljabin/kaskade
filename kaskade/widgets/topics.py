from rich.text import Text
from textual.keys import Keys

from kaskade.kafka import Kafka
from kaskade.tui_widget import TuiWidget


class Topics(TuiWidget):
    name = "Topics"
    focused = -1
    topics = []

    def __init__(self, config):
        super().__init__(name=self.name)
        self.config = config
        self.kafka = Kafka(self.config.kafka)

    def initial_state(self):
        self.focused = -1
        self.topics = self.kafka.topics()
        self.title = Text.from_markup(
            "{} ([blue]total:[/] [yellow]{}[/])".format(self.name, len(self.topics))
        )
        self.has_focus = False

    def render_content(self):
        content = Text(overflow="ellipsis")
        for index, topic in enumerate(self.topics):
            if self.focused == index:
                content.append("\u25B6", "green bold")
                content.append(topic.name, "green bold")
            else:
                content.append(" ")
                content.append(topic.name)
            content.append("\n")

        return content

    def on_key_press(self, key):
        if key == Keys.Up:
            self.focused -= 1
            if self.focused < 0:
                self.focused = len(self.topics) - 1
        elif key == Keys.Down:
            self.focused += 1
            if self.focused >= len(self.topics):
                self.focused = 0

        self.app.partitions.topic = self.topics[self.focused]
