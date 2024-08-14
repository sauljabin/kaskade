from itertools import cycle

from confluent_kafka.cimpl import NewTopic
from rich.table import Table
from textual import work
from textual.app import ComposeResult, RenderResult, App
from textual.binding import Binding
from textual.containers import Container

from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import DataTable, Input, RadioSet, RadioButton

from kaskade.banner import KaskadeBanner
from kaskade.colors import PRIMARY, SECONDARY
from kaskade.models import Topic, CleanupPolicy
from kaskade.services import (
    TopicService,
)
from kaskade.configs import (
    MILLISECONDS_1W,
    MIN_INSYNC_REPLICAS_CONFIG,
    RETENTION_MS_CONFIG,
    CLEANUP_POLICY_CONFIG,
)
from kaskade.unicodes import APPROXIMATION
from kaskade.utils import notify_error

REFRESH_TABLE_DELAY = 1
FILTER_TOPICS_SHORTCUT = "/"
BACK_SHORTCUT = "escape"
ALL_TOPICS_SHORTCUT = BACK_SHORTCUT
SUBMIT_SHORTCUT = "enter"
NEXT_SHORTCUT = ">"
SAVE_SHORTCUT = "ctrl+s"
DESCRIBE_TOPIC_SHORTCUT = SUBMIT_SHORTCUT
NEW_TOPIC_SHORTCUT = "ctrl+n"
DELETE_TOPIC_SHORTCUT = "ctrl+d"
EDIT_TOPIC_SHORTCUT = "ctrl+e"
REFRESH_TOPICS_SHORTCUT = "ctrl+r"
QUIT_SHORTCUT = "ctrl+c"


class AdminShortcuts(Widget):

    SHORTCUTS = [
        ["all:", BACK_SHORTCUT, "show:", SUBMIT_SHORTCUT],
        ["refresh:", REFRESH_TOPICS_SHORTCUT, "create:", NEW_TOPIC_SHORTCUT],
        ["filter:", FILTER_TOPICS_SHORTCUT, "edit:", EDIT_TOPIC_SHORTCUT],
        ["quit:", QUIT_SHORTCUT, "delete:", DELETE_TOPIC_SHORTCUT],
    ]

    def render(self) -> RenderResult:
        table = Table(box=None, show_header=False, padding=(0, 0, 0, 1))
        table.add_column(style=PRIMARY)
        table.add_column(style=SECONDARY)
        table.add_column(style=PRIMARY)
        table.add_column(style=SECONDARY)

        for shortcuts in self.SHORTCUTS:
            table.add_row(*shortcuts)

        return table


class Header(Widget):

    def compose(self) -> ComposeResult:
        yield AdminShortcuts()
        yield KaskadeBanner(include_version=True, include_slogan=False)


class FilterTopicsScreen(ModalScreen[str]):
    BINDINGS = [Binding(BACK_SHORTCUT, "close")]

    def compose(self) -> ComposeResult:
        input_filter = Input(placeholder="word to match")
        input_filter.border_title = "filter topics"
        input_filter.border_subtitle = f"[{PRIMARY}]filter:[/] {SUBMIT_SHORTCUT} [{SECONDARY}]|[/] [{PRIMARY}]back:[/] {BACK_SHORTCUT}"
        yield input_filter

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_close(self) -> None:
        self.dismiss()


class DeleteTopicScreen(ModalScreen[bool]):
    BINDINGS = [Binding(BACK_SHORTCUT, "cancel")]

    def __init__(self, topic: Topic):
        super().__init__()
        self.topic = topic

    def compose(self) -> ComposeResult:
        label = Input(placeholder="type the topic's name")
        label.border_title = f"delete topic [[{PRIMARY}]{self.topic}[/]]"
        label.border_subtitle = f"[{PRIMARY}]delete:[/] {SUBMIT_SHORTCUT} [{SECONDARY}]|[/] [{PRIMARY}]cancel:[/] {BACK_SHORTCUT}"
        yield label

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.topic.name == event.value:
            self.dismiss(True)
        else:
            self.notify("type the name of the topic", title="confirmation step", severity="warning")

    def action_cancel(self) -> None:
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


class EditTopicScreen(ModalScreen[bool]):
    BINDINGS = [Binding(BACK_SHORTCUT, "back"), Binding(SAVE_SHORTCUT, "edit")]

    def __init__(
        self,
        topic_name: str,
        partitions: str,
        min_insync_replicas: str,
        cleanup_policy: str,
        retention: str,
    ):
        super().__init__()
        self.topic_name = topic_name
        self.partitions = partitions
        self.min_insync_replicas = min_insync_replicas
        self.cleanup_policy = cleanup_policy
        self.retention = retention

    def compose(self) -> ComposeResult:
        input_partitions = Input(id="partitions", type="integer", value=self.partitions)
        input_partitions.border_title = "partitions"

        input_min_insync = Input(
            id="min_insync_replicas", type="integer", value=self.min_insync_replicas
        )
        input_min_insync.border_title = "min insync replicas"

        input_retention = Input(id="retention", type="integer", value=self.retention)
        input_retention.border_title = "retention (ms)"

        radio_set = RadioSet(id="cleanup")
        radio_set.border_title = "cleanup policy"

        container = Container()
        container.border_title = f"edit topic [[{PRIMARY}]{self.topic_name}[/]]"
        container.border_subtitle = f"[{PRIMARY}]save:[/] {SAVE_SHORTCUT} [{SECONDARY}]|[/] [{PRIMARY}]back:[/] {BACK_SHORTCUT}"

        with container:
            yield input_partitions
            yield input_min_insync
            yield input_retention
            with radio_set:
                yield RadioButton(
                    str(CleanupPolicy.DELETE),
                    value=self.cleanup_policy == str(CleanupPolicy.DELETE),
                )
                yield RadioButton(
                    str(CleanupPolicy.COMPACT),
                    value=self.cleanup_policy == str(CleanupPolicy.COMPACT),
                )

    def action_edit(self) -> None:
        partitions_input = self.query_one("#partitions", Input)
        self.partitions = partitions_input.value

        retention_input = self.query_one("#retention", Input)
        self.retention = retention_input.value

        min_insync_replicas_input = self.query_one("#min_insync_replicas", Input)
        self.min_insync_replicas = min_insync_replicas_input.value

        cleanup_input = self.query_one("#cleanup", RadioSet)
        self.cleanup_policy = (
            str(cleanup_input.pressed_button.label)
            if cleanup_input.pressed_button is not None
            else str(CleanupPolicy.DELETE)
        )

        self.dismiss(True)

    def action_back(self) -> None:
        self.dismiss(False)


class CreateTopicScreen(ModalScreen[NewTopic]):
    BINDINGS = [Binding(BACK_SHORTCUT, "back"), Binding(SAVE_SHORTCUT, "create")]

    def compose(self) -> ComposeResult:
        input_name = Input(id="name", placeholder="alphanumerics, '.', '_' and '-'")
        input_name.border_title = "name"

        input_partitions = Input(id="partitions", type="integer", value="1")
        input_partitions.border_title = "partitions"

        input_replication = Input(id="replicas", type="integer", value="3")
        input_replication.border_title = "replicas"

        input_min_insync = Input(id="min_insync_replicas", type="integer", value="2")
        input_min_insync.border_title = "min insync replicas"

        input_retention = Input(id="retention", type="integer", value=f"{MILLISECONDS_1W}")
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
            yield input_min_insync
            yield input_retention
            with radio_set:
                yield RadioButton(str(CleanupPolicy.DELETE), value=True)
                yield RadioButton(str(CleanupPolicy.COMPACT))

    def action_create(self) -> None:
        name_input = self.query_one("#name", Input)
        name = name_input.value

        partitions_input = self.query_one("#partitions", Input)
        partitions = partitions_input.value

        replication_input = self.query_one("#replicas", Input)
        replication = replication_input.value

        retention_input = self.query_one("#retention", Input)
        retention = retention_input.value

        min_insync_replicas_input = self.query_one("#min_insync_replicas", Input)
        min_insync_replicas = min_insync_replicas_input.value

        cleanup_input = self.query_one("#cleanup", RadioSet)
        cleanup = (
            str(cleanup_input.pressed_button.label)
            if cleanup_input.pressed_button is not None
            else str(CleanupPolicy.DELETE)
        )

        new_topic = NewTopic(
            name,
            num_partitions=int(partitions),
            replication_factor=int(replication),
            config={
                CLEANUP_POLICY_CONFIG: cleanup,
                RETENTION_MS_CONFIG: retention,
                MIN_INSYNC_REPLICAS_CONFIG: min_insync_replicas,
            },
        )

        self.dismiss(new_topic)

    def action_back(self) -> None:
        self.dismiss()


class ListTopics(Container):
    BINDINGS = [
        Binding(FILTER_TOPICS_SHORTCUT, "filter"),
        Binding(ALL_TOPICS_SHORTCUT, "all"),
        Binding(REFRESH_TOPICS_SHORTCUT, "refresh"),
        Binding(DELETE_TOPIC_SHORTCUT, "delete"),
        Binding(NEW_TOPIC_SHORTCUT, "new"),
        Binding(EDIT_TOPIC_SHORTCUT, "edit"),
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
        self.action_refresh()

    def on_data_table_row_highlighted(self, data: DataTable.RowHighlighted) -> None:
        if data.row_key.value is None:
            return
        self.current_topic = self.topics.get(data.row_key.value)

    async def refresh_table(self) -> None:
        try:
            self.topics = await self.topic_service.all()
        except Exception as ex:
            notify_error(self.app, "kafka error", ex)

        self.fill_table()

    @work
    async def action_refresh(self) -> None:
        self.start_loading_table()
        await self.refresh_table()

    def action_new(self) -> None:
        def on_dismiss(result: NewTopic | None) -> None:
            if result is None:
                return

            self.start_loading_table()

            try:
                self.topic_service.create([result])
                self.set_timer(REFRESH_TABLE_DELAY, self.refresh_table)
            except Exception as ex:
                notify_error(self.app, "kafka error", ex)

        self.app.push_screen(CreateTopicScreen(), on_dismiss)

    def start_loading_table(self) -> None:
        table = self.query_one(DataTable)
        table.loading = True

    def finish_loading_table(self) -> None:
        table = self.query_one(DataTable)
        table.loading = False

    def action_edit(self) -> None:
        if self.current_topic is None:
            return

        topic_configs = self.topic_service.get_configs(self.current_topic.name)
        min_insync_replicas = topic_configs.get(MIN_INSYNC_REPLICAS_CONFIG)
        cleanup_policy = topic_configs.get(CLEANUP_POLICY_CONFIG)
        retention = topic_configs.get(RETENTION_MS_CONFIG)

        edit_topic_screen = EditTopicScreen(
            self.current_topic.name,
            str(self.current_topic.partitions_count()),
            min_insync_replicas if min_insync_replicas else "",
            cleanup_policy if cleanup_policy else "",
            retention if retention else "",
        )

        def on_dismiss(result: bool | None) -> None:
            if not result:
                return

            if self.current_topic is None:
                return

            self.start_loading_table()

            try:
                if int(edit_topic_screen.partitions) - self.current_topic.partitions_count() > 0:
                    self.topic_service.add_partitions(
                        self.current_topic.name, int(edit_topic_screen.partitions)
                    )

                self.topic_service.edit(
                    self.current_topic.name,
                    {
                        MIN_INSYNC_REPLICAS_CONFIG: edit_topic_screen.min_insync_replicas,
                        CLEANUP_POLICY_CONFIG: edit_topic_screen.cleanup_policy,
                        RETENTION_MS_CONFIG: edit_topic_screen.retention,
                    },
                )

                self.set_timer(REFRESH_TABLE_DELAY, self.refresh_table)
            except Exception as ex:
                notify_error(self.app, "kafka error", ex)

        self.app.push_screen(edit_topic_screen, on_dismiss)

    def action_delete(self) -> None:
        if self.current_topic is None:
            return

        def on_dismiss(result: bool | None) -> None:
            if not result:
                return

            if self.current_topic is None:
                return

            self.start_loading_table()

            try:
                self.topic_service.delete(self.current_topic.name)
                self.set_timer(REFRESH_TABLE_DELAY, self.refresh_table)
            except Exception as ex:
                notify_error(self.app, "kafka error", ex)

        self.app.push_screen(DeleteTopicScreen(self.current_topic), on_dismiss)

    def action_describe(self) -> None:
        if self.current_topic is None:
            return
        self.app.push_screen(DescribeTopicScreen(self.current_topic))

    def action_all(self) -> None:
        self.current_filter = None
        self.fill_table()

    def action_filter(self) -> None:
        def on_dismiss(result: str | None) -> None:
            self.current_filter = result
            self.fill_table()

        self.app.push_screen(FilterTopicsScreen(), on_dismiss)

    def fill_table(self) -> None:
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
        table.focus()

        self.finish_loading_table()


class KaskadeAdmin(App):
    CSS_PATH = "styles.css"

    def __init__(self, kafka_config: dict[str, str]):
        super().__init__()
        self.kafka_config = kafka_config
        self.use_command_palette = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield ListTopics(TopicService(self.kafka_config))
