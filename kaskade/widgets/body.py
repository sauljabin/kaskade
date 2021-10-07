from rich.console import Group
from rich.panel import Panel
from textual.keys import Keys
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade import styles
from kaskade.renderables.paginated_table import PaginatedTable
from kaskade.renderables.topic_info import TopicInfo


class PartitionTable(PaginatedTable):
    def __init__(self, partitions, page_size=-1, page=1):
        super().__init__(len(partitions), page_size=page_size, page=page)
        self.partitions = partitions

    def render_rows(self, table, start_index, end_index):
        for partition in self.partitions[start_index:end_index]:
            table.add_row(
                str(partition.id),
                str(partition.leader),
                str(partition.replicas),
                str(partition.isrs),
            )

    def render_columns(self, table):
        table.add_column(
            "id",
            justify="right",
            style="bright_green",
            header_style="bright_green bold",
            ratio=10,
        )
        table.add_column(
            "leader", style="bright_red", header_style="bright_red bold", ratio=10
        )
        table.add_column(
            "replicas",
            style="bright_blue",
            header_style="bright_blue bold",
            ratio=40,
        )
        table.add_column(
            "in sync",
            style="bright_yellow",
            header_style="bright_yellow bold",
            ratio=40,
        )


class Body(Widget):
    has_focus = Reactive(False)
    partition_table = None

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
        partitions = len(self.app.topic.partitions())
        return TopicInfo(name=name, partitions=partitions)

    def on_key(self, event):
        if not self.partition_table:
            return

        key = event.key
        if key == Keys.PageUp:
            self.partition_table.previous()
        elif key == Keys.PageDown:
            self.partition_table.next()
        elif key == "l":
            self.partition_table.last()
        elif key == "f":
            self.partition_table.first()

    def render_body(self):
        if not self.app.topic:
            return ""

        self.partition_table = PartitionTable(
            self.app.topic.partitions(),
            page_size=self.size.height - 10,
            page=self.partition_table.page if self.partition_table else 0,
        )

        return self.partition_table

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
