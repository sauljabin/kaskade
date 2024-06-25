from itertools import cycle
from typing import List

from rich.table import Table
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


class FilterTopicsScreen(ModalScreen[str]):
    BINDINGS = [Binding(Keys.Escape, "close")]

    def compose(self) -> ComposeResult:
        yield Input()

    def on_mount(self) -> None:
        input_filter = self.query_one(Input)
        input_filter.border_title = f"[{SECONDARY}]filter[/]"
        input_filter.border_subtitle = (
            f"[{PRIMARY}]filter:[/] enter [{SECONDARY}]|[/] [{PRIMARY}]back:[/] scape"
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_close(self) -> None:
        self.dismiss()


class DescribeTopicScreen(ModalScreen):
    BINDINGS = [Binding(Keys.Escape, "close"), Binding(">", "change")]

    def __init__(self, topic: Topic):
        super().__init__()
        self.topic = topic
        self.tabs = cycle(["partitions", "groups", "group members"])
        self.current_tab = next(self.tabs)

    def compose(self) -> ComposeResult:
        yield DataTable()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.border_subtitle = f"[{PRIMARY}]next:[/] > [{SECONDARY}]|[/] [{PRIMARY}]back:[/] scape"
        self.render_partitions()

    def render_partitions(self) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.border_title = f"topic [[{PRIMARY}]{self.topic}[/]] > {self.current_tab}"
        table.add_column("id")
        table.add_column("leader")
        table.add_column("isrs")
        table.add_column("replicas")
        table.add_column("messages")

        for partition in self.topic.partitions:
            row = [
                str(partition.id),
                str(partition.leader),
                str(partition.isrs),
                str(partition.replicas),
                str(partition.messages_count()),
            ]
            table.add_row(*row)

    def render_groups(self) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.border_title = f"topic [[{PRIMARY}]{self.topic}[/]] > {self.current_tab}"
        table.add_column("id")
        table.add_column("coordinator")
        table.add_column("state")
        table.add_column("assignor")
        table.add_column("partitions")
        table.add_column("members")
        table.add_column("lag")

        for group in self.topic.groups:
            row = [
                group.id,
                str(group.coordinator) if group.coordinator else "",
                group.state,
                group.partition_assignor,
                str(group.partitions_count()),
                str(group.members_count()),
                str(group.lag_count()),
            ]
            table.add_row(*row)

    def render_group_members(self) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.border_title = f"topic [[{PRIMARY}]{self.topic}[/]] > {self.current_tab}"
        table.add_column("group")
        table.add_column("client id")
        table.add_column("member id")
        table.add_column("host")
        table.add_column("assignment")

        for group in self.topic.groups:
            for member in group.members:
                row = [
                    member.group,
                    member.client_id,
                    member.id,
                    member.host,
                    str(member.assignment),
                ]
                table.add_row(*row)

    def action_change(self) -> None:
        self.current_tab = next(self.tabs)
        method_name = self.current_tab.replace(" ", "_")
        render_table = getattr(self, f"render_{method_name}")
        render_table()

    def action_close(self) -> None:
        self.dismiss()


class ListTopics(Container):
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
        table.add_column("partitions", width=10)
        table.add_column("replicas", width=10)
        table.add_column("in sync", width=10)
        table.add_column("groups", width=10)
        table.add_column("records", width=10)
        table.add_column("lag", width=10)

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

        self.app.push_screen(FilterTopicsScreen(), on_dismiss)

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
                str(topic.partitions_count()),
                str(topic.replicas_count()),
                str(topic.isrs_count()),
                str(topic.groups_count()),
                f"{APPROXIMATION}{topic.records_count()}",
                f"{APPROXIMATION}{topic.lag()}",
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
        yield ListTopics(self.topics)
