from rich.panel import Panel
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade import styles
from kaskade.renderables.topic_info import TopicInfo


class TopicHeader(Widget):
    has_focus: Reactive = Reactive(False)

    def on_focus(self) -> None:
        self.has_focus = True

    def on_blur(self) -> None:
        self.has_focus = False

    def on_mount(self) -> None:
        self.layout_size = 4
        self.set_interval(0.2, self.refresh)

    def render(self) -> Panel:
        topic_info = TopicInfo()

        if self.app.topic is not None:
            name = self.app.topic.name
            partitions = len(self.app.topic.partitions)

            topic_info = TopicInfo(name=name, partitions=partitions)

        panel = Panel(
            topic_info,
            title="Topic",
            border_style=styles.BORDER_FOCUSED if self.has_focus else styles.BORDER,
            box=styles.BOX,
            title_align="left",
            padding=0,
        )

        return panel
