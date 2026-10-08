"""The admin topic list and its refresh and mutation orchestration."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Any, ClassVar, TypeVar

from confluent_kafka import KafkaException
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container
from textual.message import Message
from textual.widgets import DataTable

from kaskade import logger
from kaskade.admin.forms import CreateTopicScreen, EditTopicScreen
from kaskade.admin.screens import (
    BACK_SHORTCUT,
    COPY_TOPIC_SHORTCUT,
    DeleteTopicScreen,
    DescribeTopicScreen,
    FilterTopicsScreen,
    metric_value,
)
from kaskade.colors import PRIMARY
from kaskade.commands import CreateTopicCommand, UpdateTopicCommand
from kaskade.concurrency import run_blocking
from kaskade.configs import (
    CLEANUP_POLICY_CONFIG,
    MIN_INSYNC_REPLICAS_CONFIG,
    RETENTION_MS_CONFIG,
)
from kaskade.models import MetricState, Topic
from kaskade.refresh import RefreshCoordinator, RefreshReason
from kaskade.topic_service import ADMIN_EXCEPTIONS, TopicService
from kaskade.ui import copy_text, notify_error
from kaskade.unicodes import APPROXIMATION
from kaskade.widgets import TableFrame, TruncatedTooltipDataTable

T = TypeVar("T")

REFRESH_TABLE_DELAY = 1
FILTER_TOPICS_SHORTCUT = "/,ctrl+f"
ALL_TOPICS_SHORTCUT = BACK_SHORTCUT
DESCRIBE_TOPIC_SHORTCUT = "d,enter"
NEW_TOPIC_SHORTCUT = "n,ctrl+n"
DELETE_TOPIC_SHORTCUT = "ctrl+d"
EDIT_TOPIC_SHORTCUT = "e,ctrl+e"
REFRESH_TOPICS_SHORTCUT = "ctrl+r"
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


def changed_topic_config(command: UpdateTopicCommand) -> dict[str, str]:
    """Return the Kafka topic configuration entries an update changes."""
    changed_config: dict[str, str] = {}
    if command.min_insync_replicas is not None:
        changed_config[MIN_INSYNC_REPLICAS_CONFIG] = str(command.min_insync_replicas)
    if command.cleanup_policy is not None:
        changed_config[CLEANUP_POLICY_CONFIG] = command.cleanup_policy
    if command.retention_ms is not None:
        changed_config[RETENTION_MS_CONFIG] = str(command.retention_ms)
    return changed_config


class TopicDataTable(TruncatedTooltipDataTable[str]):
    """An admin topic table that reveals truncated topic names."""

    TOOLTIP_COLUMNS = frozenset({"name"})


@dataclass
class Mutation:
    """The outcome of a topic mutation that decides the follow-up refresh."""

    changed: bool = False
    error_title: str = "Kafka Error"


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

    class RefreshCompleted(Message):
        """Posted after a refresh finishes, so the app can restart periodic refreshes."""

    def __init__(self, topic_service: TopicService, *, refresh_interval: int = 0):
        super().__init__()
        self.topic_service = topic_service
        self.refresh_interval = refresh_interval
        self.topics: dict[str, Topic] = {}
        self.current_topic: Topic | None = None
        self.current_filter: str | None = None
        self.last_updated_at: datetime | None = None
        self.refresh_coordinator = RefreshCoordinator()

    def compose(self) -> ComposeResult:
        table = TopicDataTable(id="topics-table", classes="main-table")
        table.cursor_type = "row"

        table.add_column("Name", key="name", stretch=1)
        table.add_column("Partitions", key="partitions")
        table.add_column("Replicas", key="replicas")
        table.add_column("In Sync", key="isrs")
        table.add_column("Groups", key="groups")
        table.add_column("Members", key="members")
        table.add_column("Records", key="records")
        table.add_column("Lag", key="lag")

        frame = TableFrame(table, id="topics-frame", classes="kaskade-table")
        frame.border_title = rf"[{PRIMARY}]Topics[/] \[[{PRIMARY}]0[/]]"
        frame.border_subtitle = rf"\[[{PRIMARY}]Admin Mode[/]]"
        yield frame

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
        except Exception:
            logger.exception("admin refresh failed unexpectedly")
            raise
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
        self.post_message(self.RefreshCompleted())
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
        async with self._mutation(KafkaException) as mutation:
            await run_blocking(self.topic_service.create, command)
            self._notify_info("Topic Created", f"Created topic '{command.name}'")
            mutation.changed = True

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
        topic_configs = await self._load_topic_details(self.topic_service.get_configs, topic)
        if topic_configs is None:
            return

        def on_dismiss(result: UpdateTopicCommand | None) -> None:
            if result is None:
                return
            self.refresh_coordinator.begin_mutation()
            self.update_topic(topic, result)

        self.app.push_screen(EditTopicScreen(topic, topic_configs), on_dismiss)

    @work(exclusive=True, group="topic-mutation")
    async def update_topic(self, topic: Topic, command: UpdateTopicCommand) -> None:
        """Update a topic without blocking Textual's message loop."""
        async with self._mutation(KafkaException, ValueError) as mutation:
            if command.partitions > topic.partitions_count():
                await run_blocking(
                    self.topic_service.add_partitions,
                    topic.name,
                    command.partitions,
                )
                mutation.changed = True
                mutation.error_title = "Topic Partially Updated"

            changed_config = changed_topic_config(command)
            if changed_config:
                await run_blocking(self.topic_service.edit, topic.name, changed_config)
                mutation.changed = True

            if mutation.changed:
                self._notify_info("Topic Updated", f"Updated topic '{topic.name}'")
            else:
                self._notify_info("No Changes", f"No changes to topic '{topic.name}'")

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
        async with self._mutation(KafkaException) as mutation:
            await run_blocking(self.topic_service.delete, topic.name)
            self._notify_info("Topic Deleted", f"Deleted topic '{topic.name}'")
            mutation.changed = True

    @asynccontextmanager
    async def _mutation(self, *errors: type[Exception]) -> AsyncIterator[Mutation]:
        """Show loading during a mutation, report its errors, then schedule a refresh."""
        self.start_loading_table()
        mutation = Mutation()
        try:
            yield mutation
        except errors as ex:
            notify_error(self.app, mutation.error_title, ex)
        finally:
            self.finish_loading_table()
            self._finish_mutation(mutation.changed)

    def _notify_info(self, title: str, message: str) -> None:
        self.app.notify(message, title=title, severity="information")

    async def _load_topic_details(self, load: Callable[[str], T], topic: Topic) -> T | None:
        """Load topic details while the table shows loading, or report the Kafka error."""
        self.start_loading_table()
        try:
            return await run_blocking(load, topic.name)
        except KafkaException as ex:
            notify_error(self.app, "Kafka Error", ex)
            return None
        finally:
            self.finish_loading_table()

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
        configurations = await self._load_topic_details(self.topic_service.describe_configs, topic)
        if configurations is not None:
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
        self._update_table_title(len(visible_topics))
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
                for column_key, value in zip(
                    TOPIC_COLUMN_KEYS, self._topic_row(topic), strict=True
                ):
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

    def _update_table_title(self, visible_topic_count: int) -> None:
        border_title_filter_info = (
            rf"\[[{PRIMARY}]*{self.current_filter}*[/]]" if self.current_filter else ""
        )
        self.query_one("#topics-frame", TableFrame).border_title = (
            rf"[{PRIMARY}]Topics[/] {border_title_filter_info}"
            rf"\[[{PRIMARY}]{visible_topic_count}[/]]"
        )

    def _topic_row(self, topic: Topic) -> list[str]:
        return [
            topic.name,
            str(topic.partitions_count()),
            str(topic.replicas_count()),
            str(topic.isrs_count()),
            metric_value(topic.groups_state, str(topic.groups_count())),
            metric_value(topic.groups_state, str(topic.group_members_count())),
            metric_value(
                topic.records_state,
                f"{APPROXIMATION}{topic.records_count()}",
            ),
            metric_value(topic.groups_state, f"{APPROXIMATION}{topic.lag()}"),
        ]

    def _update_status(self, *, refreshing: bool) -> None:
        auto_status = f"Auto {self.refresh_interval}s" if self.refresh_interval else "Auto Off"
        if refreshing:
            state = "Refreshing…"
        elif self.last_updated_at is not None:
            state = f"Updated {self.last_updated_at:%H:%M:%S}"
        else:
            state = "Not Updated"
        self.query_one("#topics-frame", TableFrame).border_subtitle = (
            rf"\[[{PRIMARY}]Admin Mode · {state} · {auto_status}[/]]"
        )
