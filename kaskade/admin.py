import asyncio
from datetime import datetime
from time import perf_counter
from typing import Any, ClassVar

from confluent_kafka import KafkaException
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container
from textual.content import Content
from textual.validation import Function, Integer
from textual.widgets import (
    Collapsible,
    DataTable,
    Footer,
    Input,
    RadioButton,
    RadioSet,
    TabbedContent,
    TabPane,
    Tabs,
)

from kaskade import logger
from kaskade.colors import PRIMARY
from kaskade.commands import CreateTopicCommand, UpdateTopicCommand
from kaskade.configs import (
    CLEANUP_POLICY_CONFIG,
    MILLISECONDS_1W,
    MIN_INSYNC_REPLICAS_CONFIG,
    RETENTION_MS_CONFIG,
)
from kaskade.help import HelpableModalScreen, modal_bindings
from kaskade.models import CleanupPolicy, MetricState, Topic, TopicConfiguration
from kaskade.refresh import RefreshCoordinator, RefreshReason
from kaskade.services import (
    ADMIN_EXCEPTIONS,
    TopicService,
)
from kaskade.themes import KaskadeApp
from kaskade.unicodes import APPROXIMATION
from kaskade.utils import copy_text, make_it_async, notify_error
from kaskade.widgets import KaskadeHeader, StretchyDataTable

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
COPY_TOPIC_SHORTCUT = "y"
LOADING_METRIC = "…"
UNAVAILABLE_METRIC = "—"
TOPIC_COLUMN_KEYS = (
    "name",
    "partitions",
    "replicas",
    "isrs",
    "groups",
    "members",
    "records",
    "lag",
)


def _valid_topic_name(name: str) -> bool:
    return (
        0 < len(name) <= 249
        and name not in {".", ".."}
        and all(
            character.isascii() and (character.isalnum() or character in "._-")
            for character in name
        )
    )


def _valid_optional_positive_integer(value: str) -> bool:
    return not value or (value.isdigit() and int(value) >= 1)


def _input_failures(inputs: dict[str, Input]) -> list[str]:
    failures: list[str] = []
    for label, input_widget in inputs.items():
        result = input_widget.validate(input_widget.value)
        if result is not None and not result.is_valid:
            description = result.failure_descriptions[0].removesuffix(".")
            failures.append(f"{label}: {description}")
    return failures


def _focus_first_invalid(inputs: dict[str, Input]) -> None:
    first_invalid = next(
        input_widget for input_widget in inputs.values() if input_widget.has_class("-invalid")
    )
    first_invalid.focus()


class FilterTopicsScreen(HelpableModalScreen[str]):
    BINDING_GROUP_TITLE = "Filter Topics"
    AUTO_FOCUS = "#topic-filter"
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            "enter",
            "apply_filter",
            "Apply Filter",
            priority=True,
            tooltip="Apply the topic name filter.",
            id="kaskade.filter-topics.apply",
        ),
        Binding(
            BACK_SHORTCUT,
            "close",
            "Back",
            tooltip="Close the filter without applying it.",
            id="kaskade.filter-topics.close",
        ),
    )

    def compose(self) -> ComposeResult:
        input_filter = Input(
            id="topic-filter", placeholder="Topic name contains…", classes="kaskade-input"
        )
        input_filter.border_title = f"[{PRIMARY}]Filter Topics[/]"
        yield input_filter
        yield Footer(compact=True)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_apply_filter(self) -> None:
        self.dismiss(self.query_one("#topic-filter", Input).value)

    def action_close(self) -> None:
        self.dismiss()


class DeleteTopicScreen(HelpableModalScreen[bool]):
    BINDING_GROUP_TITLE = "Delete Topic"
    AUTO_FOCUS = "#topic-confirmation"
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            "enter",
            "delete",
            "Delete Topic",
            priority=True,
            tooltip="Delete the topic after its name has been confirmed.",
            id="kaskade.delete-topic.confirm",
        ),
        Binding(
            BACK_SHORTCUT,
            "cancel",
            "Cancel",
            tooltip="Keep the topic and close this confirmation.",
            id="kaskade.delete-topic.cancel",
        ),
    )

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
        self._delete_if_confirmed(event.value)

    def action_delete(self) -> None:
        self._delete_if_confirmed(self.query_one("#topic-confirmation", Input).value)

    def _delete_if_confirmed(self, confirmation: str) -> None:
        if self.topic.name == confirmation:
            self.dismiss(True)
        else:
            self.notify(
                "Type the topic name exactly to confirm deletion",
                title="Confirmation Required",
                severity="warning",
            )

    def action_cancel(self) -> None:
        self.dismiss(False)


class DescribeTopicScreen(HelpableModalScreen):
    BINDING_GROUP_TITLE = "Topic Details"
    AUTO_FOCUS = "Tabs"
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            COPY_TOPIC_SHORTCUT,
            "copy_topic",
            "Copy Selection",
            show=False,
            tooltip="Copy the selected configuration or topic name to the clipboard.",
            id="kaskade.topics.copy",
        ),
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
    )

    def __init__(
        self,
        topic: Topic,
        configurations: tuple[TopicConfiguration, ...],
    ):
        super().__init__()
        self.topic = topic
        self.configurations = configurations

    def compose(self) -> ComposeResult:
        details = TabbedContent(initial="partitions", id="topic-details")
        details.border_title = rf"[{PRIMARY}]Describe Topic[/] \[[{PRIMARY}]{self.topic.name}[/]]"
        with details:
            with TabPane(
                Content(f"Partitions [{self.topic.partitions_count()}]"),
                id="partitions",
            ):
                yield self._partitions_table()
            with TabPane(
                Content(f"Configurations [{len(self.configurations)}]"),
                id="configurations",
            ):
                yield self._configurations_table()
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

    def _configurations_table(self) -> StretchyDataTable[str]:
        table = self._new_table("configurations-table")
        table.add_column("Name", stretch=3)
        table.add_column("Value", stretch=2)

        for configuration in self._sorted_configurations():
            table.add_row(configuration.name, configuration.value)
        return table

    def _sorted_configurations(self) -> list[TopicConfiguration]:
        return sorted(self.configurations, key=lambda config: config.name.lower())

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

    def action_copy_topic(self) -> None:
        if self.query_one(TabbedContent).active == "configurations":
            table = self.query_one("#configurations-table", DataTable)
            if table.row_count == 0:
                return
            configuration = self._sorted_configurations()[table.cursor_row]
            copy_text(
                self.app,
                f"{configuration.name}={configuration.value}",
                "configuration",
            )
            return
        copy_text(self.app, self.topic.name, "topic name")

    def action_previous_tab(self) -> None:
        self.query_one(Tabs).action_previous_tab()

    def action_next_tab(self) -> None:
        self.query_one(Tabs).action_next_tab()


class EditTopicScreen(HelpableModalScreen[UpdateTopicCommand]):
    BINDING_GROUP_TITLE = "Edit Topic"
    AUTO_FOCUS = "#partitions"
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            SAVE_SHORTCUT,
            "edit",
            "Save Changes",
            tooltip="Apply the edited Kafka topic configuration.",
            id="kaskade.edit-topic.save",
        ),
        Binding(
            BACK_SHORTCUT,
            "back",
            "Back",
            tooltip="Close the editor without saving changes.",
            id="kaskade.edit-topic.close",
        ),
    )

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
            id="partitions",
            type="integer",
            value=self.partitions,
            validators=Integer(minimum=int(self.partitions)),
            classes="kaskade-input",
        )
        input_partitions.border_title = "Partitions"

        input_min_insync = Input(
            id="min_insync_replicas",
            type="integer",
            value=self.min_insync_replicas,
            validators=(
                Integer(minimum=1)
                if self.min_insync_replicas
                else Function(
                    _valid_optional_positive_integer,
                    "Enter a positive integer or leave empty when unavailable",
                )
            ),
            classes="kaskade-input",
        )
        input_min_insync.border_title = "Min In-Sync Replicas"

        input_retention = Input(
            id="retention",
            type="integer",
            value=self.retention,
            validators=Integer(minimum=-1),
            classes="kaskade-input",
        )
        input_retention.border_title = "Retention (ms)"

        radio_set = RadioSet(id="cleanup", classes="kaskade-radio")
        radio_set.border_title = "Cleanup Policy"

        container = Container(classes="topic-form")
        container.border_title = rf"[{PRIMARY}]Edit Topic[/] \[[{PRIMARY}]{self.topic_name}[/]]"

        with container:
            yield input_partitions
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
            with Collapsible(title="Advanced", id="advanced-topic-config"):
                yield input_min_insync
        yield Footer(compact=True)

    def action_edit(self) -> None:
        inputs = {
            "Partitions": self.query_one("#partitions", Input),
            "Min In-Sync Replicas": self.query_one("#min_insync_replicas", Input),
            "Retention": self.query_one("#retention", Input),
        }
        failures = _input_failures(inputs)
        if failures:
            if inputs["Min In-Sync Replicas"].has_class("-invalid"):
                self.query_one("#advanced-topic-config", Collapsible).collapsed = False
            _focus_first_invalid(inputs)
            self.notify("\n".join(failures), title="Invalid Topic", severity="warning")
            return

        cleanup_input = self.query_one("#cleanup", RadioSet)
        selected_cleanup_policy = (
            str(cleanup_input.pressed_button.label)
            if cleanup_input.pressed_button is not None
            else None
        )
        cleanup_policy = (
            selected_cleanup_policy if selected_cleanup_policy != self.cleanup_policy else None
        )

        min_insync_value = inputs["Min In-Sync Replicas"].value
        min_insync_replicas = (
            int(min_insync_value)
            if min_insync_value
            and (
                not self.min_insync_replicas
                or int(min_insync_value) != int(self.min_insync_replicas)
            )
            else None
        )

        retention_ms = int(inputs["Retention"].value)
        changed_retention_ms = retention_ms if retention_ms != int(self.retention) else None

        self.dismiss(
            UpdateTopicCommand(
                partitions=int(inputs["Partitions"].value),
                min_insync_replicas=min_insync_replicas,
                cleanup_policy=cleanup_policy,
                retention_ms=changed_retention_ms,
            )
        )

    def action_back(self) -> None:
        self.dismiss()


class CreateTopicScreen(HelpableModalScreen[CreateTopicCommand]):
    BINDING_GROUP_TITLE = "Create Topic"
    AUTO_FOCUS = "#name"
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            SAVE_SHORTCUT,
            "create",
            "Create Topic",
            tooltip="Create the topic with the configured values.",
            id="kaskade.create-topic.save",
        ),
        Binding(
            BACK_SHORTCUT,
            "back",
            "Back",
            tooltip="Close the form without creating a topic.",
            id="kaskade.create-topic.close",
        ),
    )

    def compose(self) -> ComposeResult:
        input_name = Input(
            id="name",
            placeholder="Letters, numbers, '.', '_' and '-'",
            validators=Function(
                _valid_topic_name,
                "Enter a name up to 249 characters using letters, numbers, dots, underscores, "
                "or hyphens. The name can't be empty or consist only of one or two dots",
            ),
            classes="kaskade-input",
        )
        input_name.border_title = "Name"

        input_partitions = Input(
            id="partitions",
            type="integer",
            value="1",
            validators=Integer(minimum=1),
            classes="kaskade-input",
        )
        input_partitions.border_title = "Partitions"

        input_replication = Input(
            id="replicas",
            type="integer",
            placeholder="Broker default",
            validators=Function(
                _valid_optional_positive_integer,
                "Enter a positive integer or leave empty to use the broker default",
            ),
            classes="kaskade-input",
        )
        input_replication.border_title = "Replication Factor"

        input_min_insync = Input(
            id="min_insync_replicas",
            type="integer",
            placeholder="Broker default",
            validators=Function(
                _valid_optional_positive_integer,
                "Enter a positive integer or leave empty to use the broker default",
            ),
            classes="kaskade-input",
        )
        input_min_insync.border_title = "Min In-Sync Replicas"

        input_retention = Input(
            id="retention",
            type="integer",
            value=f"{MILLISECONDS_1W}",
            validators=Integer(minimum=-1),
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
            yield input_retention
            with radio_set:
                yield RadioButton(str(CleanupPolicy.DELETE), value=True)
                yield RadioButton(str(CleanupPolicy.COMPACT))
            with Collapsible(title="Advanced", id="advanced-topic-config"):
                yield input_replication
                yield input_min_insync
        yield Footer(compact=True)

    def action_create(self) -> None:
        inputs = {
            "Name": self.query_one("#name", Input),
            "Partitions": self.query_one("#partitions", Input),
            "Replication Factor": self.query_one("#replicas", Input),
            "Min In-Sync Replicas": self.query_one("#min_insync_replicas", Input),
            "Retention": self.query_one("#retention", Input),
        }
        failures = _input_failures(inputs)

        replicas = inputs["Replication Factor"]
        min_insync_replicas = inputs["Min In-Sync Replicas"]
        if (
            not failures
            and replicas.value
            and min_insync_replicas.value
            and int(min_insync_replicas.value) > int(replicas.value)
        ):
            min_insync_replicas.add_class("-invalid")
            failures.append("Min In-Sync Replicas cannot exceed Replication Factor")

        if failures:
            if replicas.has_class("-invalid") or min_insync_replicas.has_class("-invalid"):
                self.query_one("#advanced-topic-config", Collapsible).collapsed = False
            _focus_first_invalid(inputs)
            self.notify("\n".join(failures), title="Invalid Topic", severity="warning")
            return

        cleanup_input = self.query_one("#cleanup", RadioSet)
        cleanup = (
            str(cleanup_input.pressed_button.label)
            if cleanup_input.pressed_button is not None
            else str(CleanupPolicy.DELETE)
        )

        command = CreateTopicCommand(
            name=inputs["Name"].value,
            partitions=int(inputs["Partitions"].value),
            replicas=int(replicas.value) if replicas.value else None,
            min_insync_replicas=(
                int(min_insync_replicas.value) if min_insync_replicas.value else None
            ),
            cleanup_policy=cleanup,
            retention_ms=int(inputs["Retention"].value),
        )
        self.dismiss(command)

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
            tooltip="Show topic partitions, configurations, groups, and members.",
            id="kaskade.topics.describe",
        ),
        Binding(
            COPY_TOPIC_SHORTCUT,
            "copy_topic",
            "Copy Topic",
            show=False,
            tooltip="Copy the selected topic name to the clipboard.",
            id="kaskade.topics.copy",
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
        self.last_updated_at: datetime | None = None
        self.refresh_coordinator = RefreshCoordinator()

    def compose(self) -> ComposeResult:
        table: StretchyDataTable[str] = StretchyDataTable(
            id="topics-table", classes="kaskade-table main-table"
        )
        table.cursor_type = "row"
        table.border_title = rf"[{PRIMARY}]Topics[/] \[[{PRIMARY}]0[/]]"
        table.border_subtitle = rf"\[[{PRIMARY}]Admin Mode[/]]"
        table.zebra_stripes = True

        table.add_column("Name", key="name", stretch=1)
        table.add_column("Partitions", key="partitions")
        table.add_column("Replicas", key="replicas")
        table.add_column("In Sync", key="isrs")
        table.add_column("Groups", key="groups")
        table.add_column("Members", key="members")
        table.add_column("Records", key="records")
        table.add_column("Lag", key="lag")

        yield table

    def on_mount(self) -> None:
        table = self.query_one("#topics-table", DataTable)
        table.focus()
        table.loading = True
        self._update_status(refreshing=True)

    def on_data_table_row_highlighted(self, data: DataTable.RowHighlighted) -> None:
        if data.row_key.value is None:
            return
        self.current_topic = self.topics.get(data.row_key.value)
        self.refresh_bindings()

    def action_refresh(self) -> None:
        self.request_refresh(RefreshReason.MANUAL)

    def action_copy_topic(self) -> None:
        if self.current_topic is not None:
            copy_text(self.app, self.current_topic.name, "topic name")

    def request_refresh(self, reason: RefreshReason) -> None:
        generation = self.refresh_coordinator.request(reason)
        if generation is not None:
            self._start_refresh(generation)

    def _start_refresh(self, generation: int) -> None:
        self._update_status(refreshing=True)
        self.refresh_topics(generation)

    @work(exclusive=True, group="topics-refresh")
    async def refresh_topics(self, generation: int) -> None:
        table = self.query_one(DataTable)
        if not self.topics:
            table.loading = True
        started_at = perf_counter()
        stage_tasks: list[asyncio.Task[Any]] = []

        try:
            await self._run_refresh(generation, stage_tasks, started_at)
        except ADMIN_EXCEPTIONS as ex:
            title = "Kafka Error" if isinstance(ex, KafkaException) else "Refresh Error"
            notify_error(self.app, title, ex)
        finally:
            await self._cancel_stage_tasks(stage_tasks)
            self._complete_refresh(generation, table)

    async def _run_refresh(
        self,
        generation: int,
        stage_tasks: list[asyncio.Task[Any]],
        started_at: float,
    ) -> None:
        refreshed_topics = await self.topic_service.metadata()
        self._preserve_completed_metrics(refreshed_topics)
        if not self.refresh_coordinator.is_current(generation):
            return

        self.topics = refreshed_topics
        self.fill_table()
        self.query_one(DataTable).loading = False
        offsets_task = asyncio.create_task(self.topic_service.enrich_offsets(self.topics))
        groups_task = asyncio.create_task(self.topic_service.load_groups())
        stage_tasks.extend((offsets_task, groups_task))

        failures: list[tuple[str, int]] = []
        offsets_result = await offsets_task
        if not self.refresh_coordinator.is_current(generation):
            return
        self.fill_table()
        if offsets_result.errors:
            failures.append(("record metrics", len(offsets_result.errors)))

        groups_snapshot = await groups_task
        if not self.refresh_coordinator.is_current(generation):
            return
        groups_result = self.topic_service.apply_groups(self.topics, groups_snapshot)
        self.fill_table()
        if groups_result.errors:
            failures.append(("consumer-group metrics", len(groups_result.errors)))

        self._notify_stage_failures(failures)
        self.last_updated_at = datetime.now().astimezone()
        logger.info(
            "admin refresh completed topics=%d elapsed=%.3fs",
            len(self.topics),
            perf_counter() - started_at,
        )

    @staticmethod
    async def _cancel_stage_tasks(stage_tasks: list[asyncio.Task[Any]]) -> None:
        pending_tasks = [task for task in stage_tasks if not task.done()]
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)

    def _complete_refresh(self, generation: int, table: DataTable[Any]) -> None:
        if not self.refresh_coordinator.complete(generation):
            return
        if not self.is_attached:
            return
        table.loading = False
        self._update_status(refreshing=False)
        refresh_completed = getattr(self.app, "admin_refresh_completed", None)
        if refresh_completed is not None:
            refresh_completed()
        if self.refresh_coordinator.take_pending():
            self.call_after_refresh(lambda: self.request_refresh(RefreshReason.PENDING))

    def _preserve_completed_metrics(self, refreshed_topics: dict[str, Topic]) -> None:
        for topic_name, refreshed_topic in refreshed_topics.items():
            previous_topic = self.topics.get(topic_name)
            if previous_topic is None:
                continue
            previous_partitions = {
                partition.id: partition for partition in previous_topic.partitions
            }
            if set(previous_partitions) != {
                partition.id for partition in refreshed_topic.partitions
            }:
                continue
            if previous_topic.records_state is MetricState.READY:
                for partition in refreshed_topic.partitions:
                    previous_partition = previous_partitions[partition.id]
                    partition.low = previous_partition.low
                    partition.high = previous_partition.high
                refreshed_topic.records_state = MetricState.READY
            if previous_topic.groups_state is MetricState.READY:
                refreshed_topic.groups = previous_topic.groups
                refreshed_topic.groups_state = MetricState.READY

    def _notify_stage_failures(self, failures: list[tuple[str, int]]) -> None:
        if not failures:
            return
        failure_summary = ", ".join(
            f"{stage} ({error_count} failed request(s))" for stage, error_count in failures
        )
        self.app.notify(
            f"Could not refresh {failure_summary}",
            title="Partial Refresh",
            severity="warning",
        )

    def action_new(self) -> None:
        def on_dismiss(result: CreateTopicCommand | None) -> None:
            if result is None:
                return
            self.refresh_coordinator.begin_mutation()
            self.create_topic(result)

        self.app.push_screen(CreateTopicScreen(), on_dismiss)

    @work(exclusive=True, group="topic-mutation")
    async def create_topic(self, command: CreateTopicCommand) -> None:
        """Create a topic without blocking Textual's message loop."""
        self.start_loading_table()
        refresh_after = False
        try:
            await make_it_async(self.topic_service.create, command)
            self.app.notify(
                f"Created topic '{command.name}'",
                title="Topic Created",
                severity="information",
            )
            refresh_after = True
        except KafkaException as ex:
            notify_error(self.app, "Kafka Error", ex)
        finally:
            self.finish_loading_table()
            self._finish_mutation(refresh_after)

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

        def on_dismiss(result: UpdateTopicCommand | None) -> None:
            if result is None:
                return
            self.refresh_coordinator.begin_mutation()
            self.update_topic(topic, result)

        self.app.push_screen(edit_topic_screen, on_dismiss)

    @work(exclusive=True, group="topic-mutation")
    async def update_topic(self, topic: Topic, command: UpdateTopicCommand) -> None:
        """Update a topic without blocking Textual's message loop."""
        self.start_loading_table()
        refresh_after = False
        partitions_added = False
        try:
            if command.partitions > topic.partitions_count():
                await make_it_async(
                    self.topic_service.add_partitions,
                    topic.name,
                    command.partitions,
                )
                partitions_added = True
                refresh_after = True

            changed_config: dict[str, str] = {}
            if command.min_insync_replicas is not None:
                changed_config[MIN_INSYNC_REPLICAS_CONFIG] = str(command.min_insync_replicas)
            if command.cleanup_policy is not None:
                changed_config[CLEANUP_POLICY_CONFIG] = command.cleanup_policy
            if command.retention_ms is not None:
                changed_config[RETENTION_MS_CONFIG] = str(command.retention_ms)

            if changed_config:
                await make_it_async(
                    self.topic_service.edit,
                    topic.name,
                    changed_config,
                )
                refresh_after = True

            if not refresh_after:
                self.app.notify(
                    f"No changes to topic '{topic.name}'",
                    title="No Changes",
                    severity="information",
                )
                return

            self.app.notify(
                f"Updated topic '{topic.name}'",
                title="Topic Updated",
                severity="information",
            )
        except (KafkaException, ValueError) as ex:
            title = "Topic Partially Updated" if partitions_added else "Kafka Error"
            notify_error(self.app, title, ex)
        finally:
            self.finish_loading_table()
            self._finish_mutation(refresh_after)

    def action_delete(self) -> None:
        if self.current_topic is None:
            return

        topic = self.current_topic

        def on_dismiss(result: bool | None) -> None:
            if not result:
                return
            self.refresh_coordinator.begin_mutation()
            self.delete_topic(topic)

        self.app.push_screen(DeleteTopicScreen(topic), on_dismiss)

    @work(exclusive=True, group="topic-mutation")
    async def delete_topic(self, topic: Topic) -> None:
        """Delete a topic without blocking Textual's message loop."""
        self.start_loading_table()
        refresh_after = False
        try:
            await make_it_async(self.topic_service.delete, topic.name)
            self.app.notify(
                f"Deleted topic '{topic.name}'",
                title="Topic Deleted",
                severity="information",
            )
            refresh_after = True
        except KafkaException as ex:
            notify_error(self.app, "Kafka Error", ex)
        finally:
            self.finish_loading_table()
            self._finish_mutation(refresh_after)

    def _finish_mutation(self, refresh_after: bool) -> None:
        self.refresh_coordinator.end_mutation()
        if refresh_after:
            self.refresh_coordinator.discard_pending()
            self.set_timer(
                REFRESH_TABLE_DELAY,
                lambda: self.request_refresh(RefreshReason.MUTATION),
            )
        elif self.refresh_coordinator.take_pending():
            self.call_after_refresh(lambda: self.request_refresh(RefreshReason.PENDING))

    @work(exclusive=True, group="topic-config")
    async def action_describe(self) -> None:
        if self.current_topic is None:
            return

        topic = self.current_topic
        self.start_loading_table()
        try:
            configurations = await make_it_async(
                self.topic_service.describe_configs,
                topic.name,
            )
        except KafkaException as ex:
            self.finish_loading_table()
            notify_error(self.app, "Kafka Error", ex)
            return
        self.finish_loading_table()
        self.app.push_screen(DescribeTopicScreen(topic, configurations))

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
        if action == "describe":
            return self.current_topic is not None and all(
                state is MetricState.READY
                for state in (
                    self.current_topic.records_state,
                    self.current_topic.groups_state,
                )
            )
        if action in {"copy_topic", "delete", "edit"}:
            return self.current_topic is not None
        if action == "all":
            return self.current_filter is not None
        return True

    def fill_table(self) -> None:
        table = self.query_one(DataTable)
        selected_topic_name = self.current_topic.name if self.current_topic is not None else None
        visible_topics = self._visible_topics()
        desired_keys = [topic.name for topic in visible_topics]
        self._render_topic_rows(table, visible_topics, desired_keys, selected_topic_name)
        self._restore_selection(table, desired_keys, selected_topic_name)
        self._update_table_title(table, len(visible_topics))
        self.finish_loading_table()

    def _visible_topics(self) -> list[Topic]:
        return [
            topic
            for topic in self.topics.values()
            if self.current_filter is None or self.current_filter in topic.name
        ]

    def _render_topic_rows(
        self,
        table: DataTable[Any],
        visible_topics: list[Topic],
        desired_keys: list[str],
        selected_topic_name: str | None,
    ) -> None:
        current_keys = [str(row_key.value) for row_key in table.rows]
        if current_keys == desired_keys:
            for topic in visible_topics:
                for column_key, value in zip(TOPIC_COLUMN_KEYS, self._topic_row(topic)):
                    table.update_cell(topic.name, column_key, value)
            return
        table.clear()
        for topic in visible_topics:
            table.add_row(*self._topic_row(topic), key=topic.name)
        if selected_topic_name in desired_keys:
            table.move_cursor(row=desired_keys.index(selected_topic_name), animate=False)

    def _restore_selection(
        self,
        table: DataTable[Any],
        desired_keys: list[str],
        selected_topic_name: str | None,
    ) -> None:
        if selected_topic_name in self.topics and selected_topic_name in desired_keys:
            self.current_topic = self.topics[selected_topic_name]
        elif desired_keys:
            cursor_row = min(table.cursor_row, len(desired_keys) - 1)
            self.current_topic = self.topics[desired_keys[cursor_row]]
        else:
            self.current_topic = None
        self.refresh_bindings()

    def _update_table_title(self, table: DataTable[Any], visible_topic_count: int) -> None:
        border_title_filter_info = (
            rf"\[[{PRIMARY}]*{self.current_filter}*[/]]" if self.current_filter else ""
        )
        table.border_title = (
            rf"[{PRIMARY}]Topics[/] {border_title_filter_info}"
            rf"\[[{PRIMARY}]{visible_topic_count}[/]]"
        )

    def _topic_row(self, topic: Topic) -> list[str]:
        return [
            topic.name,
            str(topic.partitions_count()),
            str(topic.replicas_count()),
            str(topic.isrs_count()),
            self._metric(topic.groups_state, str(topic.groups_count())),
            self._metric(topic.groups_state, str(topic.group_members_count())),
            self._metric(
                topic.records_state,
                f"{APPROXIMATION}{topic.records_count()}",
            ),
            self._metric(topic.groups_state, f"{APPROXIMATION}{topic.lag()}"),
        ]

    @staticmethod
    def _metric(state: MetricState, value: str) -> str:
        if state is MetricState.READY:
            return value
        if state is MetricState.UNAVAILABLE:
            return UNAVAILABLE_METRIC
        return LOADING_METRIC

    def _update_status(self, *, refreshing: bool) -> None:
        table = self.query_one(DataTable)
        interval = getattr(self.app, "auto_refresh_interval", 0)
        auto_status = f"Auto {interval}s" if interval else "Auto Off"
        if refreshing:
            state = "Refreshing…"
        elif self.last_updated_at is not None:
            state = f"Updated {self.last_updated_at:%H:%M:%S}"
        else:
            state = "Not Updated"
        table.border_subtitle = rf"\[[{PRIMARY}]Admin Mode · {state} · {auto_status}[/]]"


class KaskadeAdmin(KaskadeApp):
    TITLE = "Kaskade Admin"
    AUTO_FOCUS = "#topics-table"

    def __init__(
        self,
        kafka_config: dict[str, Any],
        refresh_interval: int | None = None,
    ):
        super().__init__()
        self.kafka_config = kafka_config
        self.auto_refresh_interval = (
            self.keymap_settings.admin_refresh_interval_seconds
            if refresh_interval is None
            else refresh_interval
        )
        self._auto_refresh_timer: Any | None = None

    def on_mount(self) -> None:
        super().on_mount()
        if self.auto_refresh_interval:
            self._auto_refresh_timer = self.set_interval(
                self.auto_refresh_interval,
                self._request_periodic_refresh,
                name="admin-auto-refresh",
                pause=True,
            )
        self.query_one(ListTopics).request_refresh(RefreshReason.INITIAL)

    def push_screen(self, *args: Any, **kwargs: Any) -> Any:
        self._pause_auto_refresh()
        return super().push_screen(*args, **kwargs)

    def pop_screen(self) -> Any:
        returning_to_topics = len(self.screen_stack) == 2
        result = super().pop_screen()
        if returning_to_topics:
            self.set_timer(0.1, self._resume_auto_refresh, name="resume-admin-auto-refresh")
        return result

    def _pause_auto_refresh(self) -> None:
        if self._auto_refresh_timer is not None:
            self._auto_refresh_timer.pause()

    def _resume_auto_refresh(self) -> None:
        if not self.auto_refresh_interval or len(self.screen_stack) != 1:
            return
        if self._auto_refresh_timer is not None:
            self._auto_refresh_timer.resume()
            self._auto_refresh_timer.reset()
        self.query_one(ListTopics).request_refresh(RefreshReason.RESUME)

    def _request_periodic_refresh(self) -> None:
        if len(self.screen_stack) == 1:
            self.query_one(ListTopics).request_refresh(RefreshReason.PERIODIC)

    def admin_refresh_completed(self) -> None:
        if self._auto_refresh_timer is not None and len(self.screen_stack) == 1:
            self._auto_refresh_timer.resume()
            self._auto_refresh_timer.reset()

    def compose(self) -> ComposeResult:
        yield KaskadeHeader(self.kafka_config)
        yield ListTopics(TopicService(self.kafka_config))
        yield Footer(compact=True)
