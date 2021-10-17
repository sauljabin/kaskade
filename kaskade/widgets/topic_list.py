from typing import Optional

from rich.panel import Panel
from rich.text import Text
from textual import events
from textual.keys import Keys
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade import styles
from kaskade.renderables.scrollable_list import ScrollableList


class TopicList(Widget):
    has_focus: Reactive = Reactive(False)
    scrollable_list: Optional[ScrollableList] = None

    def on_mount(self) -> None:
        self.set_interval(0.1, self.refresh)

    def on_focus(self) -> None:
        self.has_focus = True
        self.app.focusables.current = self

    def on_blur(self) -> None:
        self.has_focus = False

    def max_renderables_len(self) -> int:
        height: int = self.size.height
        return height - 2

    def render(self) -> Panel:
        self.scrollable_list = ScrollableList(
            self.app.topics,
            max_len=self.max_renderables_len(),
            pointer=self.scrollable_list.pointer if self.scrollable_list else -1,
        )

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

    def on_key(self, event: events.Key) -> None:
        if event.key == Keys.Up:
            self.previous()
        elif event.key == Keys.Down:
            self.next()

    def next(self) -> None:
        if self.scrollable_list is None:
            return

        self.scrollable_list.next()
        self.app.topic = self.scrollable_list.selected

    def previous(self) -> None:
        if self.scrollable_list is None:
            return

        self.scrollable_list.previous()
        self.app.topic = self.scrollable_list.selected

    async def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        await self.app.set_focus(self)
        self.next()

    async def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        await self.app.set_focus(self)
        self.previous()

    def on_click(self, event: events.Click) -> None:
        if self.scrollable_list is None:
            return

        self.scrollable_list.pointer = event.y - 1
        self.app.topic = self.scrollable_list.selected
