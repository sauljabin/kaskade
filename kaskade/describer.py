from typing import List

from rich.table import Table
from rich.text import Text
from textual import events
from textual.app import ComposeResult, RenderResult, App
from textual.containers import Container
from textual.keys import Keys
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import DataTable, Input

from kaskade.colors import PRIMARY, SECONDARY
from kaskade.models import Topic
from kaskade.services import TopicService
from kaskade.unicodes import APPROXIMATION, DOWN, LEFT, RIGHT, UP
from kaskade.widgets import KaskadeBanner


class Shortcuts(Widget):

    def on_mount(self, event: events.Mount) -> None:

        self.auto_refresh = 1 / 16

    def render(self) -> RenderResult:
        table = Table(box=None, show_header=False, padding=(0, 1, 0, 0))
        table.add_column(style=f"bold {PRIMARY}")
        table.add_column()

        table.add_row("describe", "enter")
        table.add_row("scroll", f"{LEFT} {RIGHT} {UP} {DOWN}")
        table.add_row("search", "/")
        table.add_row("quit", Keys.ControlC)
        table.add_row("all", "escape")

        return table


class Header(Widget):

    def compose(self) -> ComposeResult:
        yield KaskadeBanner(short=False, include_version=True, include_slogan=True)
        yield Shortcuts()


class SearchScreen(ModalScreen[str]):
    BINDINGS = [(Keys.Escape, "close")]

    def compose(self) -> ComposeResult:
        yield Input()

    def on_mount(self) -> None:
        search = self.query_one(Input)
        search.border_title = f"[{SECONDARY}]search[/]"
        search.border_subtitle = (
            f"[{PRIMARY}]back[/] escape [{SECONDARY}]|[/] [{PRIMARY}]search[/] enter"
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_close(self) -> None:
        self.dismiss()


class Body(Container):
    BINDINGS = [("/", "search"), (Keys.Escape, "all")]

    def __init__(self, topics: List[Topic]):
        super().__init__()
        self.topics = topics

    def compose(self) -> ComposeResult:
        yield DataTable()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.fixed_columns = 1
        table.border_subtitle = f"\\[[{PRIMARY}]describer mode[/]]"

        table.add_column("name")
        table.add_column(Text("partitions", justify="right"), width=10)
        table.add_column(Text("replicas", justify="right"), width=10)
        table.add_column(Text("in sync", justify="right"), width=10)
        table.add_column(Text("groups", justify="right"), width=10)
        table.add_column(Text("records", justify="right"), width=10)
        table.add_column(Text("lag", justify="right"), width=10)

        self.action_all()

    def action_all(self) -> None:
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

        border_title_filter_info = f" \\[[{PRIMARY}]*{with_filter}*[/]]" if with_filter else ""
        table.border_title = f"[{SECONDARY}]topics{border_title_filter_info} \\[[{PRIMARY}]{len(filtered_topics)}[/]][/]"

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


class KaskadeDescriber(App):
    CSS_PATH = "styles.css"

    def __init__(self, kafka_conf: dict[str, str]):
        super().__init__()
        topic_service = TopicService(kafka_conf)
        self.topics = topic_service.list()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Body(self.topics)
