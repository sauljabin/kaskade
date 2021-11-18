from typing import Union

from rich.align import Align
from rich.columns import Columns
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade import styles
from kaskade.renderables.topic_info import TopicInfo


class ConsumerMode(Widget):
    has_focus = Reactive(False)
    is_loading = Reactive(True)
    spinner = Spinner("dots")
    loading_text = Text("loading")

    def loading(self) -> None:
        if self.is_loading:
            self.refresh()

    def on_mount(self) -> None:
        self.set_interval(0.1, self.loading)

    def on_focus(self) -> None:
        self.has_focus = True

    def on_blur(self) -> None:
        self.has_focus = False

    def render(self) -> Panel:
        to_render: Union[Align, TopicInfo] = Align.center(
            "Not selected", vertical="middle"
        )

        if self.app.topic is not None:
            if self.is_loading:
                self.spinner.style = ""
                self.loading_text.style = ""

                if self.has_focus:
                    self.spinner.style = "magenta"
                    self.loading_text.style = "magenta"
                to_render = Align.center(
                    Columns([self.spinner, self.loading_text]), vertical="middle"
                )

        return Panel(
            to_render,
            title="consumer",
            border_style=styles.BORDER_FOCUSED if self.has_focus else styles.BORDER,
            box=styles.BOX,
            title_align="left",
            padding=0,
        )
