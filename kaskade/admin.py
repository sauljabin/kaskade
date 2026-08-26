from typing import Any, ClassVar

from confluent_kafka import KafkaException
from confluent_kafka.cimpl import NewTopic
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container
from textual.content import Content
from textual.widgets import (
    DataTable,
    Footer,
    Input,
    RadioButton,
    RadioSet,
    TabbedContent,
    TabPane,
    Tabs,
)

from kaskade.colors import PRIMARY
from kaskade.configs import (
    CLEANUP_POLICY_CONFIG,
    MILLISECONDS_1W,
    MIN_INSYNC_REPLICAS_CONFIG,
    RETENTION_MS_CONFIG,
)
from kaskade.help import HelpableModalScreen
from kaskade.models import CleanupPolicy, Topic
from kaskade.services import (
    TopicService,
)
from kaskade.themes import KaskadeApp
from kaskade.unicodes import APPROXIMATION
from kaskade.utils import make_it_async, notify_error
from kaskade.widgets import StretchyDataTable

REFRESH_TABLE_DELAY = 1
FILTER_TOPICS_SHORTCUT = "/,ctrl+f"
BACK_SHORTCUT = "escape"
ALL_TOPICS_SHORTCUT = BACK_SHORTCUT
SAVE_SHORTCUT = "ctrl+s"
DESCRIBE_TOPIC_SHORTCUT = "d,enter"
NEW_TOPIC_SHORTCUT = "n,ctrl+n"
DELETE_TOPIC_SHORTCUT = "ctrl+d"
EDIT_TOPIC_SHORTCUT = "e,ctrl+e"
REFRESH_TOPICS_SHORTCUT = "ctrl+r"


class FilterTopicsScreen(HelpableModalScreen[str]):
    BINDING_GROUP_TITLE = "Filter Topics"
    AUTO_FOCUS = "#topic-filter"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            BACK_SHORTCUT,
            "close",
            "Back",
            tooltip="Close the filter without applying it.",
            id="kaskade.filter-topics.close",
        )
    ]

    def compose(self) -> ComposeResult:
        input_filter = Input(
            id="topic-filter", placeholder="Topic name contains…", classes="kaskade-input"
        )
        input_filter.border_title = f"[{PRIMARY}]Filter Topics[/]"
        yield input_filter
        yield Footer(compact=True)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_close(self) -> None:
        self.dismiss()


class DeleteTopicScreen(HelpableModalScreen[bool]):
    BINDING_GROUP_TITLE = "Delete Topic"
    AUTO_FOCUS = "#topic-confirmation"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            BACK_SHORTCUT,
            "cancel",
            "Cancel",
            tooltip="Keep the topic and close this confirmation.",
            id="kaskade.delete-topic.cancel",
        )
    ]

    def __init__(self, topic: Topic):
        super().__init__()
        self.topic = topic

    def compose(self) -> ComposeResult:
        label = Input(
            id="topic-confirmation",
            placeholder="Type the topic name to confirm",
            classes="kaskade-input",
        )
        label.border_title = rf"[{PRIMARY}]Delete Topic[/] \[[{PRIMARY}]{self.topic}[/]]"
        yield label
        yield Footer(compact=True)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.topic.name == event.value:
            self.dismiss(True)
        else:
            self.notify(
                "Type the topic name exactly to confirm deletion.",
                title="Confirmation Required",
                severity="warning",
            )

    def action_cancel(self) -> None:
        self.dismiss(False)


class DescribeTopicScreen(HelpableModalScreen):
    BINDING_GROUP_TITLE = "Topic Details"
    AUTO_FOCUS = "Tabs"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            BACK_SHORTCUT,
            "close",
            "Back",
            tooltip="Close the topic details.",
            id="kaskade.describe-topic.close",
        ),
        Binding(
            "h",
            "previous_tab",
            "Previous Tab",
            show=False,
            tooltip="Show the previous topic detail tab.",
            id="kaskade.navigation.left",
        ),
        Binding(
            "l",
            "next_tab",
            "Next Tab",
            show=False,
            tooltip="Show the next topic detail tab.",
            id="kaskade.navigation.right",
        ),
    ]

    def __init__(self, topic: Topic):
        super().__init__()
        self.topic = topic

    def compose(self) -> ComposeResult:
        details = TabbedContent(initial="partitions", id="topic-details")
        details.border_title = rf"[{PRIMARY}]Describe Topic[/] \[[{PRIMARY}]{self.topic.name}[/]]"
        with details:
            with TabPane(
                Content(f"Partitions [{self.topic.partitions_count()}]"),
                id="partitions",
            ):
                yield self._partitions_table()
            with TabPane(Content(f"Groups [{self.topic.groups_count()}]"), id="groups"):
                yield self._groups_table()
            with TabPane(
                Content(f"Group Members [{self.topic.group_members_count()}]"),
                id="group-members",
            ):
                yield self._group_members_table()
        yield Footer(compact=True)

    def _new_table(self, table_id: str) -> StretchyDataTable[str]:
        table: StretchyDataTable[str] = StretchyDataTable(id=table_id, classes="details-table")
        table.cursor_type = "row"
        table.zebra_stripes = True
        return table

    def _partitions_table(self) -> StretchyDataTable[str]:
        table = self._new_table("partitions-table")
        table.add_column("ID", stretch=1)
        table.add_column("Leader", stretch=1)
        table.add_column("ISRs", stretch=1)
        table.add_column("Replicas", stretch=1)
        table.add_column("Records", stretch=1)

        for partition in self.topic.partitions:
            table.add_row(
                str(partition.id),
                str(partition.leader),
                str(partition.isrs),
                str(partition.replicas),
                str(partition.records_count()),
            )
        return table

    def _groups_table(self) -> StretchyDataTable[str]:
        table = self._new_table("groups-table")
        table.add_column("ID", stretch=1)
        table.add_column("Coordinator", stretch=1)
        table.add_column("State", stretch=1)
        table.add_column("Assignor", stretch=1)
        table.add_column("Partitions", stretch=1)
        table.add_column("Members", stretch=1)
        table.add_column("Lag", stretch=1)

        for group in self.topic.groups:
            table.add_row(
                group.id,
                str(group.coordinator) if group.coordinator else "",
                group.state,
                group.partition_assignor,
                str(group.partitions_count()),
                str(group.members_count()),
                str(group.lag_count()),
            )
        return table

    def _group_members_table(self) -> StretchyDataTable[str]:
        table = self._new_table("group-members-table")
        table.add_column("Group", stretch=1)
        table.add_column("Client ID", stretch=1)
        table.add_column("Member ID", stretch=1)
        table.add_column("Host", stretch=1)
        table.add_column("Assignment", stretch=1)

        for group in self.topic.groups:
            for member in group.members:
                table.add_row(
                    member.group,
                    member.client_id,
                    member.id,
                    member.host,
                    str(member.assignment),
                )
        return table

    def action_close(self) -> None:
        self.dismiss()

    def action_previous_tab(self) -> None:
        self.query_one(Tabs).action_previous_tab()

    def action_next_tab(self) -> None:
        self.query_one(Tabs).action_next_tab()


class EditTopicScreen(HelpableModalScreen[bool]):
    BINDING_GROUP_TITLE = "Edit Topic"
    AUTO_FOCUS = "#partitions"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            BACK_SHORTCUT,
            "back",
            "Back",
            tooltip="Close the editor without saving changes.",
            id="kaskade.edit-topic.close",
        ),
        Binding(
            SAVE_SHORTCUT,
            "edit",
            "Save Changes",
            tooltip="Apply the edited Kafka topic configuration.",
            id="kaskade.edit-topic.save",
        ),
    ]

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
        input_partitions = Input(
            id="partitions", type="integer", value=self.partitions, classes="kaskade-input"
        )
        input_partitions.border_title = "Partitions"

        input_min_insync = Input(
            id="min_insync_replicas",
            type="integer",
            value=self.min_insync_replicas,
            classes="kaskade-input",
        )
        input_min_insync.border_title = "Min In-Sync Replicas"

        input_retention = Input(
            id="retention", type="integer", value=self.retention, classes="kaskade-input"
        )
        input_retention.border_title = "Retention (ms)"

        radio_set = RadioSet(id="cleanup", classes="kaskade-radio")
        radio_set.border_title = "Cleanup Policy"

        container = Container(classes="topic-form")
        container.border_title = rf"[{PRIMARY}]Edit Topic[/] \[[{PRIMARY}]{self.topic_name}[/]]"

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
        yield Footer(compact=True)

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


class CreateTopicScreen(HelpableModalScreen[NewTopic]):
    BINDING_GROUP_TITLE = "Create Topic"
    AUTO_FOCUS = "#name"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            BACK_SHORTCUT,
            "back",
            "Back",
            tooltip="Close the form without creating a topic.",
            id="kaskade.create-topic.close",
        ),
        Binding(
            SAVE_SHORTCUT,
            "create",
            "Create Topic",
            tooltip="Create the topic with the configured values.",
            id="kaskade.create-topic.save",
        ),
    ]

    def compose(self) -> ComposeResult:
        input_name = Input(
            id="name",
            placeholder="Letters, numbers, '.', '_' and '-'",
            classes="kaskade-input",
        )
        input_name.border_title = "Name"

        input_partitions = Input(
            id="partitions", type="integer", value="1", classes="kaskade-input"
        )
        input_partitions.border_title = "Partitions"

        input_replication = Input(id="replicas", type="integer", value="3", classes="kaskade-input")
        input_replication.border_title = "Replicas"

        input_min_insync = Input(
            id="min_insync_replicas", type="integer", value="2", classes="kaskade-input"
        )
        input_min_insync.border_title = "Min In-Sync Replicas"

        input_retention = Input(
            id="retention",
            type="integer",
            value=f"{MILLISECONDS_1W}",
            classes="kaskade-input",
        )
        input_retention.border_title = "Retention (ms)"

        radio_set = RadioSet(id="cleanup", classes="kaskade-radio")
        radio_set.border_title = "Cleanup Policy"

        container = Container(classes="topic-form")
        container.border_title = f"[{PRIMARY}]Create Topic[/]"

        with container:
            yield input_name
            yield input_partitions
            yield input_replication
            yield input_min_insync
            yield input_retention
            with radio_set:
                yield RadioButton(str(CleanupPolicy.DELETE), value=True)
                yield RadioButton(str(CleanupPolicy.COMPACT))
        yield Footer(compact=True)

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
            topic=name,
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
    BINDING_GROUP_TITLE = "Topics"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            DESCRIBE_TOPIC_SHORTCUT,
            "describe",
            "Describe",
            priority=True,
            key_display="d",
            tooltip="Show partitions, groups, and members for the selected topic.",
            id="kaskade.topics.describe",
        ),
        Binding(
            FILTER_TOPICS_SHORTCUT,
            "filter",
            "Filter",
            key_display="/",
            tooltip="Filter topics by name.",
            id="kaskade.topics.filter",
        ),
        Binding(
            REFRESH_TOPICS_SHORTCUT,
            "refresh",
            "Refresh",
            tooltip="Reload topic metadata from Kafka.",
            id="kaskade.topics.refresh",
        ),
        Binding(
            NEW_TOPIC_SHORTCUT,
            "new",
            "Create",
            key_display="n",
            tooltip="Open the topic creation form.",
            id="kaskade.topics.create",
        ),
        Binding(
            EDIT_TOPIC_SHORTCUT,
            "edit",
            "Edit",
            key_display="e",
            show=False,
            tooltip="Edit the selected topic configuration.",
            id="kaskade.topics.edit",
        ),
        Binding(
            DELETE_TOPIC_SHORTCUT,
            "delete",
            "Delete",
            show=False,
            tooltip="Delete the selected topic after confirmation.",
            id="kaskade.topics.delete",
        ),
        Binding(
            ALL_TOPICS_SHORTCUT,
            "all",
            "Show All",
            show=False,
            tooltip="Clear the active topic filter.",
            id="kaskade.topics.show-all",
        ),
    ]

    def __init__(self, topic_service: TopicService):
        super().__init__()
        self.topic_service = topic_service
        self.topics: dict[str, Topic] = {}
        self.current_topic: Topic | None = None
        self.current_filter: str | None = None

    def compose(self) -> ComposeResult:
        table: StretchyDataTable[str] = StretchyDataTable(
            id="topics-table", classes="kaskade-table main-table"
        )
        table.cursor_type = "row"
        table.border_title = rf"[{PRIMARY}]Topics[/] \[[{PRIMARY}]0[/]]"
        table.border_subtitle = rf"\[[{PRIMARY}]Admin Mode[/]]"
        table.zebra_stripes = True

        table.add_column("Name", stretch=1)
        table.add_column("Partitions")
        table.add_column("Replicas")
        table.add_column("In Sync")
        table.add_column("Groups")
        table.add_column("Members")
        table.add_column("Records")
        table.add_column("Lag")

        yield table

    def on_mount(self) -> None:
        self.query_one("#topics-table", DataTable).focus()
        self.action_refresh()

    def on_data_table_row_highlighted(self, data: DataTable.RowHighlighted) -> None:
        if data.row_key.value is None:
            return
        self.current_topic = self.topics.get(data.row_key.value)
        self.refresh_bindings()

    async def refresh_table(self) -> None:
        try:
            self.topics = await self.topic_service.all()
        except KafkaException as ex:
            notify_error(self.app, "Kafka Error", ex)

        self.fill_table()

    @work(exclusive=True, group="topics-refresh")
    async def action_refresh(self) -> None:
        self.start_loading_table()
        await self.refresh_table()

    def action_new(self) -> None:
        def on_dismiss(result: NewTopic | None) -> None:
            if result is None:
                return
            self.create_topic(result)

        self.app.push_screen(CreateTopicScreen(), on_dismiss)

    @work(exclusive=True, group="topic-mutation")
    async def create_topic(self, topic: NewTopic) -> None:
        """Create a topic without blocking Textual's message loop."""
        self.start_loading_table()
        try:
            await make_it_async(self.topic_service.create, [topic])
            self.app.notify(
                f"Created topic '{topic.topic}'.",
                title="Topic Created",
                severity="information",
            )
            self.set_timer(REFRESH_TABLE_DELAY, self.refresh_table)
        except KafkaException as ex:
            self.finish_loading_table()
            notify_error(self.app, "Kafka Error", ex)

    def start_loading_table(self) -> None:
        table = self.query_one(DataTable)
        table.loading = True

    def finish_loading_table(self) -> None:
        table = self.query_one(DataTable)
        table.loading = False

    @work(exclusive=True, group="topic-config")
    async def action_edit(self) -> None:
        if self.current_topic is None:
            return

        topic = self.current_topic
        self.start_loading_table()
        try:
            topic_configs = await make_it_async(self.topic_service.get_configs, topic.name)
        except KafkaException as ex:
            self.finish_loading_table()
            notify_error(self.app, "Kafka Error", ex)
            return
        self.finish_loading_table()

        min_insync_replicas = topic_configs.get(MIN_INSYNC_REPLICAS_CONFIG)
        cleanup_policy = topic_configs.get(CLEANUP_POLICY_CONFIG)
        retention = topic_configs.get(RETENTION_MS_CONFIG)

        edit_topic_screen = EditTopicScreen(
            topic.name,
            str(topic.partitions_count()),
            min_insync_replicas if min_insync_replicas else "",
            cleanup_policy if cleanup_policy else "",
            retention if retention else "",
        )

        def on_dismiss(result: bool | None) -> None:
            if not result:
                return
            self.update_topic(topic, edit_topic_screen)

        self.app.push_screen(edit_topic_screen, on_dismiss)

    @work(exclusive=True, group="topic-mutation")
    async def update_topic(self, topic: Topic, editor: EditTopicScreen) -> None:
        """Update a topic without blocking Textual's message loop."""
        self.start_loading_table()
        try:
            partition_count = int(editor.partitions)
            if partition_count > topic.partitions_count():
                await make_it_async(self.topic_service.add_partitions, topic.name, partition_count)

            await make_it_async(
                self.topic_service.edit,
                topic.name,
                {
                    MIN_INSYNC_REPLICAS_CONFIG: editor.min_insync_replicas,
                    CLEANUP_POLICY_CONFIG: editor.cleanup_policy,
                    RETENTION_MS_CONFIG: editor.retention,
                },
            )
            self.app.notify(
                f"Updated topic '{topic.name}'.",
                title="Topic Updated",
                severity="information",
            )
            self.set_timer(REFRESH_TABLE_DELAY, self.refresh_table)
        except (KafkaException, ValueError) as ex:
            self.finish_loading_table()
            notify_error(self.app, "Kafka Error", ex)

    def action_delete(self) -> None:
        if self.current_topic is None:
            return

        topic = self.current_topic

        def on_dismiss(result: bool | None) -> None:
            if not result:
                return
            self.delete_topic(topic)

        self.app.push_screen(DeleteTopicScreen(topic), on_dismiss)

    @work(exclusive=True, group="topic-mutation")
    async def delete_topic(self, topic: Topic) -> None:
        """Delete a topic without blocking Textual's message loop."""
        self.start_loading_table()
        try:
            await make_it_async(self.topic_service.delete, topic.name)
            self.app.notify(
                f"Deleted topic '{topic.name}'.",
                title="Topic Deleted",
                severity="information",
            )
            self.set_timer(REFRESH_TABLE_DELAY, self.refresh_table)
        except KafkaException as ex:
            self.finish_loading_table()
            notify_error(self.app, "Kafka Error", ex)

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

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Disable contextual actions when their required state is unavailable."""
        if action in {"delete", "describe", "edit"}:
            return self.current_topic is not None
        if action == "all":
            return self.current_filter is not None
        return True

    def fill_table(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        self.current_topic = None
        self.refresh_bindings()

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
                str(topic.group_members_count()),
                f"{APPROXIMATION}{topic.records_count()}",
                f"{APPROXIMATION}{topic.lag()}",
            ]
            table.add_row(*row, key=topic.name)

        border_title_filter_info = (
            rf"\[[{PRIMARY}]*{self.current_filter}*[/]]" if self.current_filter else ""
        )
        table.border_title = (
            rf"[{PRIMARY}]Topics[/] {border_title_filter_info}\[[{PRIMARY}]{total_count}[/]]"
        )

        self.finish_loading_table()


class KaskadeAdmin(KaskadeApp):
    TITLE = "Kaskade Admin"
    AUTO_FOCUS = "#topics-table"

    def __init__(self, kafka_config: dict[str, Any]):
        super().__init__()
        self.kafka_config = kafka_config

    def compose(self) -> ComposeResult:
        yield ListTopics(TopicService(self.kafka_config))
        yield Footer(compact=True)
