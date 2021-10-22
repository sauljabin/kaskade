import re
from typing import Callable, Optional

from rich.panel import Panel
from rich.text import Text
from textual import events
from textual.keys import Keys
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade import styles
from kaskade.renderables.groups_table import GroupsTable
from kaskade.renderables.paginated_table import PaginatedTable
from kaskade.renderables.partitions_table import PartitionsTable
from kaskade.utils.circular_list import CircularList

CLICK_OFFSET = 2

TABLE_BOTTOM_PADDING = 4

TITLE_LEFT_PADDING = 3


class Tab:
    def __init__(self, name: str, render: Callable[[], None]):
        self.name = name
        self.render = render


class TopicDetail(Widget):
    has_focus = Reactive(False)
    table: Optional[PaginatedTable] = None

    def __init__(self, name: Optional[str] = None):
        super().__init__(name)
        self.tabs = CircularList(
            [
                Tab("partitions", self.render_partitions),
                Tab("groups", self.render_groups),
            ]
        )
        self.tabs.index = 0

    def render_partitions(self) -> None:
        page = 1
        row = 0

        if self.table is not None:
            page = self.table.page
            row = self.table.row

        self.table = PartitionsTable(
            self.app.topic.partitions if self.app.topic else [],
            page_size=self.size.height - TABLE_BOTTOM_PADDING,
            page=page,
            row=row,
        )

    def render_groups(self) -> None:
        page = 1
        row = 0

        if self.table is not None:
            page = self.table.page
            row = self.table.row

        self.table = GroupsTable(
            self.app.topic.groups if self.app.topic else [],
            page_size=self.size.height - TABLE_BOTTOM_PADDING,
            page=page,
            row=row,
        )

    def title(self) -> Text:
        return Text.from_markup(
            " ── ".join(
                [
                    "[bold]{}[/]".format(tab.name)
                    if tab == self.tabs.current
                    else "[dim white]{}[/]".format(tab.name)
                    for tab in self.tabs.list
                ]
            )
        )

    def render(self) -> Panel:
        if self.tabs.current is not None:
            self.tabs.current.render()

        body_panel = Panel(
            self.table if self.table is not None else "",
            title=self.title(),
            border_style=styles.BORDER_FOCUSED if self.has_focus else styles.BORDER,
            box=styles.BOX,
            title_align="left",
            padding=0,
        )

        return body_panel

    def on_focus(self) -> None:
        self.has_focus = True
        self.app.focusables.current = self

    def on_blur(self) -> None:
        self.has_focus = False

    def on_key(self, event: events.Key) -> None:
        if self.table is None:
            return

        key = event.key
        if key == Keys.PageUp:
            self.table.previous_page()
        elif key == Keys.PageDown:
            self.table.next_page()
        elif key == "f":
            self.table.first_page()
        elif key == "l":
            self.table.last_page()
        elif key == Keys.Up:
            self.table.previous_row()
        elif key == Keys.Down:
            self.table.next_row()
        elif key == "]":
            self.next_tab()
        elif key == "[":
            self.previous_tab()

        self.refresh()

    def next_tab(self) -> None:
        self.tabs.next()
        self.table = None

    def previous_tab(self) -> None:
        self.tabs.previous()
        self.table = None

    async def on_mouse_scroll_up(self) -> None:
        await self.app.set_focus(self)
        if self.table is not None:
            self.table.next_row()

        self.refresh()

    async def on_mouse_scroll_down(self) -> None:
        await self.app.set_focus(self)
        if self.table is not None:
            self.table.previous_row()

        self.refresh()

    def on_click(self, event: events.Click) -> None:
        if self.table is not None:
            self.table.row = event.y - CLICK_OFFSET

        if event.y == 0:
            title = self.title().plain
            for tab in self.tabs.list:
                for start, end in [
                    (f.start(), f.start() + len(tab.name))
                    for f in re.finditer(tab.name, title)
                ]:
                    if start <= event.x - TITLE_LEFT_PADDING < end:
                        self.tabs.current = tab
                        self.table = None

        self.refresh()
