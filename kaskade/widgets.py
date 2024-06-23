from typing import List

from pyfiglet import Figlet
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult, RenderResult
from textual.containers import Container
from textual.keys import Keys
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import DataTable, Input

from kaskade import APP_NAME, APP_VERSION
from kaskade.colors import PRIMARY, SECONDARY, THIRD
from kaskade.models import Cluster, Topic
from kaskade.unicodes import APPROXIMATION


class Shortcuts(Widget):
    def __init__(self, cluster: Cluster):
        super().__init__()
        self.cluster = cluster

    def render(self) -> RenderResult:
        table = Table(box=None, show_header=False, padding=(0, 0, 0, 1))
        table.add_column(style=f"bold {PRIMARY}", justify="right")
        table.add_column()

        table.add_row("cluster id:", self.cluster.id)
        table.add_row("controller:", str(self.cluster.controller))
        table.add_row("nodes:", str(len(self.cluster.nodes)))
        table.add_row("help:", "?")
        table.add_row("quit:", Keys.ControlC)

        return table


class KaskadeBanner(Widget):
    def __init__(self, include_version: bool = False, include_slogan: bool = False):
        super().__init__()
        self.include_slogan = include_slogan
        self.include_version = include_version

    def render(self) -> Text:
        figlet = Figlet(font="standard")
        text = Text(figlet.renderText(APP_NAME).rstrip(), style=f"{PRIMARY} bold")

        if self.include_version:
            text.append(f"\nv{APP_VERSION}", style=f"{SECONDARY}")

        if self.include_slogan:
            text.append("\na kafka text user interface", style=f"{SECONDARY}")

        return text


class Header(Widget):
    def __init__(self, cluster: Cluster):
        super().__init__()
        self.cluster = cluster

    def compose(self) -> ComposeResult:
        yield KaskadeBanner(include_version=True)
        yield Shortcuts(self.cluster)


class SearchScreen(ModalScreen[str]):
    BINDINGS = [(Keys.Escape, "close")]

    def compose(self) -> ComposeResult:
        yield Input()

    def on_mount(self) -> None:
        search = self.query_one(Input)
        search.border_title = f"[{SECONDARY}]search[/]"

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_close(self) -> None:
        self.dismiss()


class Body(Container):
    BINDINGS = [("/", "search")]

    def __init__(self, topics: List[Topic]):
        super().__init__()
        self.topics = topics

    def compose(self) -> ComposeResult:
        yield DataTable()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.fixed_columns = 1

        table.add_column("name")
        table.add_column(Text("partitions", justify="right"), width=10)
        table.add_column(Text("replicas", justify="right"), width=10)
        table.add_column(Text("in sync", justify="right"), width=10)
        table.add_column(Text("groups", justify="right"), width=10)
        table.add_column(Text("records", justify="right"), width=10)
        table.add_column(Text("lag", justify="right"), width=10)

        self.run_worker(self.fill_table(), exclusive=True)

    def action_search(self) -> None:
        def on_dismiss(result: str) -> None:
            self.run_worker(self.fill_table(result), exclusive=True)

        self.app.push_screen(SearchScreen(), on_dismiss)

    async def fill_table(self, with_filter: None | str = None) -> None:
        filtered_topics = [
            topic for topic in self.topics if not with_filter or with_filter in topic.name
        ]
        table = self.query_one(DataTable)
        table.clear()
        table.border_title = f"[{SECONDARY}]topics ([{PRIMARY}]{len(filtered_topics)}[/])[/]{f" <[{THIRD}]{with_filter}[/]>" if with_filter else ""}"

        for topic in filtered_topics:
            row = [
                topic.name,
                Text(str(topic.partitions_count()), justify="right"),
                Text(str(topic.replicas_count()), justify="right"),
                Text(str(topic.isrs_count()), justify="right"),
                Text(str(topic.groups_count()), justify="right"),
                Text(
                    f"{APPROXIMATION}{topic.records_count()}",
                    justify="right",
                ),
                Text(
                    f"{APPROXIMATION}{topic.lag()}",
                    justify="right",
                ),
            ]
            table.add_row(*row, key=topic.name)
