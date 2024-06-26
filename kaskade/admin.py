import asyncio
from itertools import cycle

from confluent_kafka import KafkaException
from rich.table import Table
from textual.app import ComposeResult, RenderResult, App
from textual.binding import Binding
from textual.containers import Container
from textual.keys import Keys
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import DataTable, Input, Label

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
        table.add_column(style=PRIMARY)
        table.add_column(style=SECONDARY)

        table.add_row(
            "describe:",
            "enter",
            "create:",
            Keys.ControlN,
        )
        table.add_row("scroll:", f"{LEFT} {RIGHT} {UP} {DOWN}", "delete:", Keys.ControlD)
        table.add_row("filter:", "/", "refresh:", Keys.ControlR)
        table.add_row("all:", "escape", "quit:", Keys.ControlC)

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
        input_filter.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_close(self) -> None:
        self.dismiss()


class ConfirmationScreen(ModalScreen[bool]):
    BINDINGS = [Binding(Keys.Escape, "no"), Binding(Keys.Enter, "yes")]

    def compose(self) -> ComposeResult:
        yield Label("Are you sure?")

    def on_mount(self) -> None:
        label = self.query_one(Label)
        label.border_subtitle = (
            f"[{PRIMARY}]yes:[/] enter [{SECONDARY}]|[/] [{PRIMARY}]no:[/] scape"
        )
        label.focus()

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)


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
        Binding(Keys.ControlR, "refresh"),
        Binding(Keys.ControlD, "delete"),
        Binding(Keys.Enter, "describe", priority=True),
    ]

    def __init__(self, kafka_conf: dict[str, str]):
        super().__init__()
        self.topic_service = TopicService(kafka_conf)
        self.topics: dict[str, Topic] = {}
        self.current_topic: Topic | None = None
        self.current_filter: str | None = None

    def compose(self) -> ComposeResult:
        yield DataTable()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.border_subtitle = f"\\[[{PRIMARY}]admin mode[/]]"
        table.zebra_stripes = True

        table.add_column("name")
        table.add_column("partitions", width=10)
        table.add_column("replicas", width=10)
        table.add_column("in sync", width=10)
        table.add_column("groups", width=10)
        table.add_column("records", width=10)
        table.add_column("lag", width=10)

        self.run_worker(self.action_refresh())

    def on_data_table_row_highlighted(self, data: DataTable.RowHighlighted) -> None:
        if data.row_key.value is None:
            return
        self.current_topic = self.topics.get(data.row_key.value)

    async def action_refresh(self) -> None:
        table = self.query_one(DataTable)
        table.loading = True

        try:
            self.topics = self.topic_service.all()
        except Exception as ex:
            self.notify_error(ex)
        self.run_worker(self.fill_table())

    async def action_delete(self) -> None:
        if self.current_topic is None:
            return

        async def on_dismiss(result: bool) -> None:
            if not result:
                return

            if self.current_topic is None:
                return

            try:
                self.topic_service.delete(self.current_topic.name)
                await asyncio.sleep(0.5)
                self.run_worker(self.action_refresh())
            except Exception as ex:
                self.notify_error(ex)

        await self.app.push_screen(ConfirmationScreen(), on_dismiss)

    def notify_error(self, ex: Exception) -> None:
        if isinstance(ex, KafkaException):
            message = ex.args[0].str()
        else:
            message = str(ex)
        self.notify(message, severity="error", title="kafka error")

    def action_describe(self) -> None:
        if self.current_topic is None:
            return
        self.app.push_screen(DescribeTopicScreen(self.current_topic))

    def action_all(self) -> None:
        self.current_filter = None
        self.run_worker(self.fill_table())

    def action_filter(self) -> None:
        def on_dismiss(result: str) -> None:
            self.current_filter = result
            self.run_worker(self.fill_table())

        self.app.push_screen(FilterTopicsScreen(), on_dismiss)

    async def fill_table(self) -> None:
        table = self.query_one(DataTable)
        table.clear()

        total_count = 0
        for topic in self.topics.values():
            if self.current_filter is not None and self.current_filter not in topic.name:
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

        border_title_filter_info = (
            f"\\[[{PRIMARY}]*{self.current_filter}*[/]]" if self.current_filter else ""
        )
        table.border_title = (
            f"[{SECONDARY}]topics {border_title_filter_info}\\[[{PRIMARY}]{total_count}[/]][/]"
        )
        table.loading = False
        table.focus()


class KaskadeAdmin(App):
    CSS_PATH = "styles.css"

    def __init__(self, kafka_conf: dict[str, str]):
        super().__init__()
        self.kafka_conf = kafka_conf

    def on_mount(self) -> None:
        self.use_command_palette = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield ListTopics(self.kafka_conf)
