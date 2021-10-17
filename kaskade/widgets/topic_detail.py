from typing import Optional, Union

from rich.panel import Panel
from textual import events
from textual.keys import Keys
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade import styles
from kaskade.renderables.partitions_table import PartitionsTable


class TopicDetail(Widget):
    has_focus = Reactive(False)
    partitions_table: Optional[PartitionsTable] = None

    def on_focus(self) -> None:
        self.has_focus = True
        self.app.focusables.current = self

    def on_blur(self) -> None:
        self.has_focus = False

    def on_key(self, event: events.Key) -> None:
        if self.partitions_table is None:
            return

        key = event.key
        if key == Keys.PageUp:
            self.partitions_table.previous_page()
        elif key == Keys.PageDown:
            self.partitions_table.next_page()
        elif key == "f":
            self.partitions_table.first_page()
        elif key == "l":
            self.partitions_table.last_page()
        elif key == Keys.Up:
            self.partitions_table.previous_row()
        elif key == Keys.Down:
            self.partitions_table.next_row()

        self.refresh()

    def render_body(self) -> Union[PartitionsTable, str]:
        if not self.app.topic:
            return ""

        page = 0
        row = 0

        if self.partitions_table is not None:
            page = self.partitions_table.page
            row = self.partitions_table.row

        self.partitions_table = PartitionsTable(
            self.app.topic.partitions,
            page_size=self.size.height - 5,
            page=page,
            row=row,
        )

        return self.partitions_table

    def render(self) -> Panel:
        body_panel = Panel(
            self.render_body(),
            title="Partitions",
            border_style=styles.BORDER_FOCUSED if self.has_focus else styles.BORDER,
            box=styles.BOX,
            title_align="left",
            padding=0,
        )

        return body_panel

    async def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        await self.app.set_focus(self)

        if self.partitions_table is None:
            return

        self.partitions_table.next_row()
        self.refresh()

    async def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        await self.app.set_focus(self)

        if self.partitions_table is None:
            return

        self.partitions_table.previous_row()
        self.refresh()

    def on_click(self, event: events.Click) -> None:
        if self.partitions_table is None:
            return

        self.partitions_table.row = event.y - 2
        self.refresh()
