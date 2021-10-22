from typing import Union

from rich.align import Align
from rich.panel import Panel
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade import styles
from kaskade.renderables.topic_info import TopicInfo

PANEL_SIZE = 5


class TopicHeader(Widget):
    has_focus: Reactive = Reactive(False)

    def on_focus(self) -> None:
        self.has_focus = True
        self.app.focusables.current = self

    def on_blur(self) -> None:
        self.has_focus = False

    def on_mount(self) -> None:
        self.layout_size = PANEL_SIZE

    def render(self) -> Panel:
        topic_info: Union[Align, TopicInfo] = Align.center(
            "Not selected", vertical="middle"
        )

        if self.app.topic is not None:
            topic_info = TopicInfo(self.app.topic)

        panel = Panel(
            topic_info,
            title="topic",
            border_style=styles.BORDER_FOCUSED if self.has_focus else styles.BORDER,
            box=styles.BOX,
            title_align="left",
            padding=0,
        )

        return panel
