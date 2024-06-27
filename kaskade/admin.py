import asyncio
from itertools import cycle

from confluent_kafka import KafkaException
from confluent_kafka.cimpl import NewTopic
from rich.table import Table
from textual.app import ComposeResult, RenderResult, App
from textual.binding import Binding
from textual.containers import Container

from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import DataTable, Input, Label, RadioSet, RadioButton

from kaskade import logger
from kaskade.colors import PRIMARY, SECONDARY
from kaskade.models import Topic
from kaskade.services import TopicService, MILLISECONDS_24H
from kaskade.unicodes import APPROXIMATION, DOWN, LEFT, RIGHT, UP
from kaskade.widgets import KaskadeBanner

FILTER_TOPICS_ACTION = "/"
BACK_SHORTCUT = "escape"
ALL_TOPICS_SHORTCUT = BACK_SHORTCUT
SUBMIT_SHORTCUT = "enter"
NEXT_SHORTCUT = ">"
SAVE_SHORTCUT = "ctrl+s"
DESCRIBE_TOPIC_SHORTCUT = SUBMIT_SHORTCUT
NEW_TOPIC_SHORTCUT = "ctrl+n"
DELETE_TOPIC_SHORTCUT = "ctrl+d"
REFRESH_TOPICS_SHORTCUT = "ctrl+r"
QUIT_SHORTCUT = "ctrl+c"


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
            NEW_TOPIC_SHORTCUT,
        )
        table.add_row("scroll:", f"{LEFT} {RIGHT} {UP} {DOWN}", "delete:", DELETE_TOPIC_SHORTCUT)
        table.add_row("filter:", "/", "refresh:", REFRESH_TOPICS_SHORTCUT)
        table.add_row("all:", "escape", "quit:", QUIT_SHORTCUT)

        return table


class Header(Widget):

    def compose(self) -> ComposeResult:
        yield KaskadeBanner(short=True, include_version=True, include_slogan=False)
        yield Shortcuts()


class FilterTopicsScreen(ModalScreen[str]):
    BINDINGS = [Binding(BACK_SHORTCUT, "close")]

    def compose(self) -> ComposeResult:
        input_filter = Input()
        input_filter.border_title = "filter topic"
        input_filter.border_subtitle = f"[{PRIMARY}]filter:[/] {SUBMIT_SHORTCUT} [{SECONDARY}]|[/] [{PRIMARY}]back:[/] {BACK_SHORTCUT}"
        yield input_filter

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_close(self) -> None:
        self.dismiss()


class ConfirmationScreen(ModalScreen[bool]):
    BINDINGS = [Binding(BACK_SHORTCUT, "no"), Binding(SUBMIT_SHORTCUT, "yes")]

    def compose(self) -> ComposeResult:
        label = Label("Are you sure?")
        label.border_title = "delete topic"
        label.border_subtitle = f"[{PRIMARY}]yes:[/] {SUBMIT_SHORTCUT} [{SECONDARY}]|[/] [{PRIMARY}]no:[/] {BACK_SHORTCUT}"
        yield label

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)


class DescribeTopicScreen(ModalScreen):
    BINDINGS = [Binding(BACK_SHORTCUT, "close"), Binding(NEXT_SHORTCUT, "next")]

    def __init__(self, topic: Topic):
        super().__init__()
        self.topic = topic
        self.tabs = cycle(["partitions", "groups", "group members"])

    def compose(self) -> ComposeResult:
        table: DataTable = DataTable()
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.border_subtitle = f"[{PRIMARY}]next:[/] {NEXT_SHORTCUT} [{SECONDARY}]|[/] [{PRIMARY}]back:[/] {BACK_SHORTCUT}"
        yield table

    def on_mount(self) -> None:
        self.action_next()

    def render_partitions(self) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.border_title = f"partitions [[{PRIMARY}]{self.topic}[/]]\\[[{PRIMARY}]{self.topic.partitions_count()}[/]]"
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
        table.border_title = (
            f"groups [[{PRIMARY}]{self.topic}[/]]\\[[{PRIMARY}]{self.topic.groups_count()}[/]]"
        )
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
        table.border_title = f"group members [[{PRIMARY}]{self.topic}[/]]\\[[{PRIMARY}]{self.topic.group_members_count()}[/]]"
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

    def action_next(self) -> None:
        current_tab = next(self.tabs)
        method_name = current_tab.replace(" ", "_")
        render_table = getattr(self, f"render_{method_name}")
        render_table()

    def action_close(self) -> None:
        self.dismiss()


class CreateTopicScreen(ModalScreen[NewTopic]):
    BINDINGS = [Binding(BACK_SHORTCUT, "back"), Binding(SAVE_SHORTCUT, "create")]

    def compose(self) -> ComposeResult:
        input_name = Input(id="name")
        input_name.border_title = "name"

        input_partitions = Input(id="partitions", type="integer", value="1")
        input_partitions.border_title = "partitions"

        input_replication = Input(id="replication", type="integer", value="1")
        input_replication.border_title = "replication"

        input_retention = Input(id="retention", type="integer", value=f"{MILLISECONDS_24H}")
        input_retention.border_title = "retention (ms)"

        radio_set = RadioSet(id="cleanup")
        radio_set.border_title = "cleanup policy"

        container = Container()
        container.border_title = "create topic"
        container.border_subtitle = f"[{PRIMARY}]create:[/] {SAVE_SHORTCUT} [{SECONDARY}]|[/] [{PRIMARY}]back:[/] {BACK_SHORTCUT}"

        with container:
            yield input_name
            yield input_partitions
            yield input_replication
            yield input_retention
            with radio_set:
                yield RadioButton("delete", value=True)
                yield RadioButton("compact")

    def action_create(self) -> None:
        name_input = self.query_one("#name", Input)
        name = name_input.value

        partitions_input = self.query_one("#partitions", Input)
        partitions = partitions_input.value

        replication_input = self.query_one("#replication", Input)
        replication = replication_input.value

        retention_input = self.query_one("#retention", Input)
        retention = retention_input.value

        cleanup_input = self.query_one("#cleanup", RadioSet)
        cleanup = (
            cleanup_input.pressed_button.label
            if cleanup_input.pressed_button is not None
            else "delete"
        )

        new_topic = NewTopic(
            name,
            num_partitions=int(partitions),
            replication_factor=int(replication),
            config={"cleanup.policy": cleanup, "delete.retention.ms": retention},
        )

        self.dismiss(new_topic)

    def action_back(self) -> None:
        self.dismiss()


class ListTopics(Container):
    BINDINGS = [
        Binding(FILTER_TOPICS_ACTION, "filter"),
        Binding(ALL_TOPICS_SHORTCUT, "all"),
        Binding(REFRESH_TOPICS_SHORTCUT, "refresh"),
        Binding(DELETE_TOPIC_SHORTCUT, "delete"),
        Binding(NEW_TOPIC_SHORTCUT, "new"),
        Binding(DESCRIBE_TOPIC_SHORTCUT, "describe", priority=True),
    ]

    def __init__(self, topic_service: TopicService):
        super().__init__()
        self.topic_service = topic_service
        self.topics: dict[str, Topic] = {}
        self.current_topic: Topic | None = None
        self.current_filter: str | None = None

    def compose(self) -> ComposeResult:
        table: DataTable = DataTable()
        table.cursor_type = "row"
        table.border_title = f"[{SECONDARY}]topics \\[[{PRIMARY}]0[/]][/]"
        table.border_subtitle = f"\\[[{PRIMARY}]admin mode[/]]"
        table.zebra_stripes = True

        table.add_column("name")
        table.add_column("partitions", width=10)
        table.add_column("replicas", width=10)
        table.add_column("in sync", width=10)
        table.add_column("groups", width=10)
        table.add_column("records", width=10)
        table.add_column("lag", width=10)

        yield table

    def on_mount(self) -> None:
        self.run_worker(self.action_refresh())

    def on_data_table_row_highlighted(self, data: DataTable.RowHighlighted) -> None:
        if data.row_key.value is None:
            return
        self.current_topic = self.topics.get(data.row_key.value)

    async def action_refresh(self) -> None:
        table = self.query_one(DataTable)
        table.loading = True

        try:
            self.topics = await self.topic_service.all()
        except Exception as ex:
            self.notify_error("kafka error", ex)
        self.run_worker(self.fill_table())

    async def action_new(self) -> None:
        async def on_dismiss(result: NewTopic) -> None:
            if result is None:
                return

            try:
                self.topic_service.create([result])
                await asyncio.sleep(0.5)
                self.run_worker(self.action_refresh())
            except Exception as ex:
                self.notify_error("kafka error", ex)

        await self.app.push_screen(CreateTopicScreen(), on_dismiss)

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
                self.notify_error("kafka error", ex)

        await self.app.push_screen(ConfirmationScreen(), on_dismiss)

    def notify_error(self, title: str, ex: Exception) -> None:
        if isinstance(ex, KafkaException):
            message = ex.args[0].str()
        else:
            message = str(ex)
        logger.exception(ex)
        self.notify(message, severity="error", title=title)

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
        self.use_command_palette = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield ListTopics(TopicService(self.kafka_conf))
