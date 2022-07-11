from typing import Union

from rich.align import Align
from rich.panel import Panel

from kaskade import styles
from kaskade.renderables.topic_info import TopicInfo
from kaskade.widgets.tui_widget import TuiWidget

PANEL_SIZE = 5


class TopicHeader(TuiWidget):
    def on_mount(self) -> None:
        self.layout_size = PANEL_SIZE

    def render(self) -> Panel:
        topic_info: Union[Align, TopicInfo] = Align.center(
            "Not selected", vertical="middle"
        )

        if self.tui.topic is not None:
            topic_info = TopicInfo(self.tui.topic)

        panel = Panel(
            topic_info,
            title="[bold]topic[/]",
            border_style=styles.BORDER,
            box=styles.BOX,
            title_align="left",
            padding=0,
        )

        return panel
