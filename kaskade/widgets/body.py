from rich.console import Group
from rich.panel import Panel
from textual.keys import Keys
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade import styles
from kaskade.renderables.partitions_table import PartitionsTable
from kaskade.renderables.topic_info import TopicInfo


class Body(Widget):
    has_focus = Reactive(False)
    partitions_table = None

    def on_mount(self):
        self.set_interval(0.1, self.refresh)

    def on_focus(self):
        self.has_focus = True

    def on_blur(self):
        self.has_focus = False

    def render_header(self):
        if not self.app.topic:
            return ""

        name = self.app.topic.name
        partitions = len(self.app.topic.partitions)
        return TopicInfo(name=name, partitions=partitions)

    def on_key(self, event):
        if not self.partitions_table:
            return

        key = event.key
        if key == Keys.PageUp:
            self.partitions_table.previous()
        elif key == Keys.PageDown:
            self.partitions_table.next()
        elif key == Keys.ControlPageUp:
            self.partitions_table.first()
        elif key == Keys.ControlPageDown:
            self.partitions_table.last()

    def render_body(self):
        if not self.app.topic:
            return ""

        self.partitions_table = PartitionsTable(
            self.app.topic.partitions,
            page_size=self.size.height - 10,
            page=self.partitions_table.page if self.partitions_table else 0,
        )

        return self.partitions_table

    def render(self):
        header_height = 4
        border_style = styles.BORDER_FOCUSED if self.has_focus else styles.BORDER

        header_panel = Panel(
            self.render_header(),
            title="Topic",
            border_style=border_style,
            box=styles.BOX,
            title_align="left",
            height=header_height,
            padding=0,
        )

        body_panel = Panel(
            self.render_body(),
            title="Partitions",
            border_style=border_style,
            box=styles.BOX,
            title_align="left",
            height=self.size.height - header_height,
            padding=0,
        )

        return Group(header_panel, body_panel)
