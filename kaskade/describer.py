from typing import List

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult, RenderResult, App
from textual.binding import Binding
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

    def render(self) -> RenderResult:
        table = Table(box=None, show_header=False, padding=(0, 1, 0, 0))
        table.add_column(style=PRIMARY)
        table.add_column(style=SECONDARY)

        table.add_row("describe:", "enter")
        table.add_row("scroll:", f"{LEFT} {RIGHT} {UP} {DOWN}")
        table.add_row("filter:", "/")
        table.add_row("quit:", Keys.ControlC)
        table.add_row("all:", "escape")

        return table


class Header(Widget):

    def compose(self) -> ComposeResult:
        yield KaskadeBanner(short=True, include_version=True, include_slogan=False)
        yield Shortcuts()


class SearchTopicScreen(ModalScreen[str]):
    BINDINGS = [Binding(Keys.Escape, "close")]

    def compose(self) -> ComposeResult:
        yield Input()

    def on_mount(self) -> None:
        input_filter = self.query_one(Input)
        input_filter.border_title = f"[{SECONDARY}]filter[/]"
        input_filter.border_subtitle = (
            f"[{PRIMARY}]back:[/] scape [{SECONDARY}]|[/] [{PRIMARY}]filter:[/] enter"
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_close(self) -> None:
        self.dismiss()


class DescribeTopicScreen(ModalScreen):
    BINDINGS = [Binding(Keys.Escape, "close")]

    def __init__(self, topic: Topic):
        super().__init__()
        self.topic = topic

    def compose(self) -> ComposeResult:
        yield Container()

    def on_mount(self) -> None:
        table = self.query_one(Container)
        table.border_title = f"topic \\[[{PRIMARY}]{self.topic.name}[/]]"
        table.border_subtitle = f"[{PRIMARY}]back:[/] scape"

    def action_close(self) -> None:
        self.dismiss()


class DescribeTopicBody(Container):
    BINDINGS = [
        Binding("/", "filter"),
        Binding(Keys.Escape, "all"),
        Binding(Keys.Enter, "describe", priority=True),
    ]

    def __init__(self, topics: List[Topic]):
        super().__init__()
        self.topics = {topic.name: topic for topic in topics}
        self.current_topic: Topic | None = None

    def compose(self) -> ComposeResult:
        yield DataTable()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.border_subtitle = f"\\[[{PRIMARY}]describer mode[/]]"
        table.zebra_stripes = True

        table.add_column("name")
        table.add_column(Text("partitions", justify="right"), width=10)
        table.add_column(Text("replicas", justify="right"), width=10)
        table.add_column(Text("in sync", justify="right"), width=10)
        table.add_column(Text("groups", justify="right"), width=10)
        table.add_column(Text("records", justify="right"), width=10)
        table.add_column(Text("lag", justify="right"), width=10)

        self.action_all()

    def on_data_table_row_highlighted(self, data: DataTable.RowHighlighted) -> None:
        if data.row_key.value is None:
            return
        self.current_topic = self.topics.get(data.row_key.value)

    def action_describe(self) -> None:
        if self.current_topic is None:
            return
        self.app.push_screen(DescribeTopicScreen(self.current_topic))

    def action_all(self) -> None:
        self.run_worker(self.fill_table())

    def action_filter(self) -> None:
        def on_dismiss(result: str) -> None:
            self.run_worker(self.fill_table(result))

        self.app.push_screen(SearchTopicScreen(), on_dismiss)

    async def fill_table(self, with_filter: None | str = None) -> None:
        table = self.query_one(DataTable)
        table.clear()

        total_count = 0
        for topic in self.topics.values():
            if with_filter is not None and with_filter not in topic.name:
                continue
            total_count += 1
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

        border_title_filter_info = f"\\[[{PRIMARY}]*{with_filter}*[/]]" if with_filter else ""
        table.border_title = (
            f"[{SECONDARY}]topics {border_title_filter_info}\\[[{PRIMARY}]{total_count}[/]][/]"
        )
        table.focus()


class KaskadeDescriber(App):
    CSS_PATH = "styles.css"

    def __init__(self, kafka_conf: dict[str, str]):
        super().__init__()
        topic_service = TopicService(kafka_conf)
        self.topics = topic_service.all()

    def on_mount(self) -> None:
        self.use_command_palette = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield DescribeTopicBody(self.topics)
