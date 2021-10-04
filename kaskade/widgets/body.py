from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade import styles


class Body(Widget):
    topic = None
    has_focus = Reactive(False)

    def on_mount(self):
        self.set_interval(0.1, self.refresh)
        self.initial_state()

    def on_focus(self):
        self.has_focus = True

    def on_blur(self):
        self.has_focus = False

    def render(self):
        return self.render_content()

    def render_header(self):
        content = ""
        if self.topic:
            content = Table(box=None, expand=False, show_header=False, show_edge=False)
            content.add_column(style="magenta bold")
            content.add_column(style="yellow bold")
            content.add_row("name:", self.topic.name)
            content.add_row("size:", "unknown")
            content.add_row("count:", "unknown")

        return content

    def render_body(self):
        content = ""
        if self.topic:
            content = Table(
                expand=True,
                box=box.SIMPLE_HEAD,
                row_styles=["none", "dim"],
                show_edge=False,
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
        header_height = 5
        header_panel = Panel(
            self.render_header(),
            title="Topic",
            border_style=styles.BORDER_FOCUSED if self.has_focus else styles.BORDER,
            box=styles.BOX,
            title_align="left",
            height=header_height,
            padding=0,
        )

        body_panel = Panel(
            self.render_body(),
            title="Partitions",
            border_style=styles.BORDER_FOCUSED if self.has_focus else styles.BORDER,
            box=styles.BOX,
            title_align="left",
            height=self.size.height - header_height,
            padding=0,
        )

        return Group(header_panel, body_panel)

    def initial_state(self):
        self.topic = None
        self.has_focus = False

    def on_key_press(self, key):
        pass
