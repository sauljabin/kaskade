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
        self.topics = dict(
            sorted(self.kafka.topics().items(), key=lambda item: item[0])
        )
        self.has_focus = False

    def render_content(self):
        content = Text(overflow="ellipsis")
        for index, val in enumerate(self.topics):
            if self.focused == index:
                content.append("\u25B6", "green bold")
                content.append(val, "green bold")
            else:
                content.append(" ")
                content.append(val)
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

        self.app.data.topic = list(self.topics.items())[self.focused]
