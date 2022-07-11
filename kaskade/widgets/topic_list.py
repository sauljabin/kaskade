from typing import Optional, Union

from rich.align import Align
from rich.panel import Panel
from rich.text import Text
from textual import events
from textual.keys import Keys
from textual.reactive import Reactive

from kaskade import styles
from kaskade.kafka.models import Topic
from kaskade.renderables.scrollable_list import ScrollableList
from kaskade.widgets.tui_widget import TuiWidget


class TopicList(TuiWidget):
    has_focus: Reactive[bool] = Reactive(False)
    scrollable_list: Optional[ScrollableList[Topic]] = None

    def max_renderables_len(self) -> int:
        height: int = self.size.height
        return height - 2

    def render(self) -> Panel:
        to_render: Union[Align, ScrollableList[Topic]] = Align.center(
            "Topics not found", vertical="middle"
        )

        if self.tui.topics:
            self.scrollable_list = ScrollableList(
                self.tui.topics,
                max_len=self.max_renderables_len(),
                selected=self.scrollable_list.selected
                if self.scrollable_list
                else None,
            )
            to_render = self.scrollable_list

        title = Text.from_markup(
            "[bold]topics[/] ([blue]total[/] [yellow]{}[/])".format(
                len(self.tui.topics)
            )
        )
        return Panel(
            to_render,
            title=title,
            border_style=styles.BORDER_FOCUSED if self.has_focus else styles.BORDER,
            box=styles.BOX,
            title_align="left",
        )

    def next(self) -> None:
        if self.scrollable_list is None:
            return

        self.scrollable_list.next()
        self.tui.topic = self.scrollable_list.selected

        self.tui.enable_describer_mode()

    def previous(self) -> None:
        if self.scrollable_list is None:
            return

        self.scrollable_list.previous()
        self.tui.topic = self.scrollable_list.selected

        self.tui.enable_describer_mode()

    def on_focus(self) -> None:
        self.has_focus = True
        self.tui.focusables.current = self

    def on_blur(self) -> None:
        self.has_focus = False

    def on_key(self, event: events.Key) -> None:
        if event.key == Keys.Up:
            self.previous()
        elif event.key == Keys.Down:
            self.next()

        self.refresh()

    async def on_mouse_scroll_up(self) -> None:
        await self.tui.set_focus(self)
        self.next()
        self.refresh()

    async def on_mouse_scroll_down(self) -> None:
        await self.tui.set_focus(self)
        self.previous()
        self.refresh()

    async def on_click(self, event: events.Click) -> None:
        if self.scrollable_list is not None:
            self.scrollable_list.pointer = event.y - 1
            self.tui.topic = self.scrollable_list.selected

        self.tui.enable_describer_mode()

        self.refresh()
