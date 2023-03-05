from typing import Type

from rich.columns import Columns
from rich.console import RenderableType
from rich.markdown import Markdown
from rich.text import Text
from textual.app import App, ComposeResult, CSSPathType
from textual.binding import Binding
from textual.containers import Container
from textual.driver import Driver
from textual.keys import Keys
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static

from kaskade.config import Config
from kaskade.kafka.cluster_service import ClusterService
from kaskade.kafka.models import Cluster
from kaskade.kafka.topic_service import TopicService
from kaskade.renderables.cluster_info import ClusterInfo
from kaskade.renderables.kaskade_name import KaskadeName
from kaskade.styles.unicodes import DOWN, UP


class Help(Screen):
    BINDINGS = [Binding("escape,space,q,question_mark", "pop_screen", "Close")]

    md_doc = f"""
# Help
## Navigation
- **navigate**: {UP} {DOWN}
- **focus on next**: {Keys.Tab}
- **quit**: {Keys.ControlC}
- **help window**: ?
- **close dialog**: {Keys.Escape}
    """

    def compose(self) -> ComposeResult:
        yield Static(Markdown(self.md_doc))


class Header(Static):
    cluster = Cluster()

    def render(self) -> RenderableType:
        kaskade_name = KaskadeName()
        cluster_info = ClusterInfo(self.cluster)
        return Columns([kaskade_name, cluster_info], padding=3)


class Title(Static):
    message: Text = Text()

    def render(self) -> RenderableType:
        return self.message


class Body(Container):
    pass


class Tui(App[None]):
    CSS_PATH = "tui.css"
    SCREENS = {"help": Help}
    BINDINGS = [
        Binding(Keys.ControlC, "quit", "quit"),
        Binding("question_mark", "push_screen('help')", "help", key_display="?"),
    ]

    def __init__(
        self,
        config: Config,
        driver_class: Type[Driver] | None = None,
        css_path: CSSPathType | None = None,
        watch_css: bool = False,
    ):
        super().__init__(driver_class, css_path, watch_css)
        self.config = config

        self.topic_service = TopicService(self.config)
        self.cluster_service = ClusterService(self.config)

        self.cluster = self.cluster_service.current()
        self.topics = self.topic_service.list()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(Title(), Body(DataTable()))
        yield Footer()

    def on_mount(self) -> None:
        header = self.query_one(Header)
        header.cluster = self.cluster

        title = self.query_one(Title)
        title.message = Text.from_markup(f"[bold]total topics:[/] {len(self.topics)}")

        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.fixed_columns = 1

        table.add_column("name")
        table.add_column("partitions", width=10)
        table.add_column("replicas", width=10)
        table.add_column("in sync", width=10)
        table.add_column("groups", width=10)
        table.add_column("records", width=10)
        table.add_column("lag", width=10)
        for topic in self.topics:
            row = [
                f"[b]{topic.name}[/b]",
                topic.partitions_count(),
                topic.replicas_count(),
                topic.isrs_count(),
                topic.groups_count(),
                topic.messages_count(),
                topic.lag_count(),
            ]
            table.add_row(*row)
