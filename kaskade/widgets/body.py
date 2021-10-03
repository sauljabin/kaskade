from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table

from kaskade.tui_widget import TuiWidget


class Body(TuiWidget):
    name = "Body"
    topic = None

    def __init__(self):
        super().__init__(name=self.name)

    def render(self):
        return self.render_content()

    def render_header(self):
        content = ""
        if self.topic:
            content = Table(box=None, expand=False, padding=0)
            content.add_column(style="magenta bold")
            content.add_column(style="yellow bold")
            content.add_row("name:", self.topic.name)
            content.add_row("size:", "100mb")
            content.add_row("count:", "\u22481000")

        return content

    def render_body(self):
        content = ""
        if self.topic:
            content = Table(
                expand=True,
                box=box.SIMPLE_HEAD,
                row_styles=["none", "dim"],
            )

            content.add_column(
                "id",
                justify="right",
                style="bright_green",
                header_style="bright_green bold",
                ratio=10,
            )
            content.add_column(
                "leader", style="bright_red", header_style="bright_red bold", ratio=10
            )
            content.add_column(
                "replicas",
                style="bright_blue",
                header_style="bright_blue bold",
                ratio=40,
            )
            content.add_column(
                "in sync",
                style="bright_yellow",
                header_style="bright_yellow bold",
                ratio=40,
            )

            for partition in self.topic.partitions():
                content.add_row(
                    str(partition.id),
                    str(partition.leader),
                    str(partition.replicas),
                    str(partition.isrs),
                )

        return content

    def render_content(self):
        header_height = 7
        header_panel = Panel(
            self.render_header(),
            title="Topic",
            border_style=self.border_style(),
            box=box.SQUARE,
            title_align="left",
            height=header_height,
        )

        body_panel = Panel(
            self.render_body(),
            title="Partitions",
            border_style=self.border_style(),
            box=box.SQUARE,
            title_align="left",
            height=self.size.height - header_height,
        )

        return Group(header_panel, body_panel)

    def initial_state(self):
        self.topic = None
        self.has_focus = False
