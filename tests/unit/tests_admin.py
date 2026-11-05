import asyncio
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from confluent_kafka import KafkaError, KafkaException
from textual.coordinate import Coordinate
from textual.widgets import (
    Collapsible,
    DataTable,
    Input,
    RadioButton,
    RadioSet,
    Static,
    TabbedContent,
)
from textual.worker import WorkerFailed

from kaskade.admin import (
    CreateTopicScreen,
    DeleteGroupScreen,
    DescribeTopicScreen,
    EditTopicScreen,
    FilterTopicsScreen,
    KaskadeAdmin,
    ListTopics,
    ResetOffsetsScreen,
    ReviewOffsetResetScreen,
    ReviewTopicChangesScreen,
)
from kaskade.admin.forms import parse_partitions, parse_timestamp, partitions_placeholder
from kaskade.admin.screens import GroupAction, GroupActionKind
from kaskade.admin.topics import DETAILS_LOADING_DELAY, REFRESH_TABLE_DELAY, TopicDataTable
from kaskade.commands import (
    ConfigChange,
    CreateTopicCommand,
    OffsetTarget,
    ResetOffsetsCommand,
    UpdateTopicCommand,
)
from kaskade.configs import (
    CLEANUP_POLICY_CONFIG,
    MIN_INSYNC_REPLICAS_CONFIG,
    RETENTION_MS_CONFIG,
)
from kaskade.group_service import (
    GroupNotEmptyError,
    OffsetReset,
    OffsetResetOutcome,
    OffsetResetPlan,
)
from kaskade.help import contextual_help
from kaskade.models import (
    Group,
    GroupMember,
    GroupPartition,
    MetricState,
    Node,
    Partition,
    Topic,
    TopicConfiguration,
)
from kaskade.refresh import RefreshCoordinator, RefreshReason
from kaskade.settings import SETTINGS_ENV_VAR, load_settings
from kaskade.topic_service import EnrichmentResult, GroupSnapshot
from kaskade.widgets import TableFrame
from tests import configure_admin_service


def edit_topic_screen(
    *,
    min_insync_replicas: str = "2",
    cleanup_policy: str = "delete",
    retention_overridden: bool = True,
) -> EditTopicScreen:
    """Edit a three-partition topic that overrides min.insync.replicas.

    Its cleanup policy is the cluster default, and a missing min.insync.replicas
    has an empty value.
    """
    configurations = [
        TopicConfiguration(CLEANUP_POLICY_CONFIG, cleanup_policy),
        TopicConfiguration(RETENTION_MS_CONFIG, "1000", overridden=retention_overridden),
    ]
    if min_insync_replicas:
        configurations.append(
            TopicConfiguration(MIN_INSYNC_REPLICAS_CONFIG, min_insync_replicas, overridden=True)
        )
    topic = Topic(name="orders", partitions=[Partition(id=index) for index in range(3)])
    return EditTopicScreen(topic, configurations)


async def save_and_apply(pilot: Any, key: str = "ctrl+s") -> None:
    """Save the edit form, then apply its changes from Review Changes."""
    await pilot.press(key)
    await pilot.pause()
    assert isinstance(pilot.app.screen, ReviewTopicChangesScreen)
    await pilot.press(key)
    await pilot.pause()


class TestRefreshCoordinator(unittest.TestCase):
    def test_coalesces_non_periodic_requests(self) -> None:
        coordinator = RefreshCoordinator()

        generation = coordinator.request(RefreshReason.INITIAL)

        self.assertEqual(1, generation)
        self.assertIsNone(coordinator.request(RefreshReason.MANUAL))
        self.assertIsNone(coordinator.request(RefreshReason.RESUME))
        self.assertTrue(coordinator.pending)
        self.assertTrue(coordinator.complete(1))
        self.assertTrue(coordinator.take_pending())
        self.assertFalse(coordinator.take_pending())

    def test_skips_periodic_requests_during_active_work(self) -> None:
        coordinator = RefreshCoordinator()
        coordinator.request(RefreshReason.INITIAL)

        self.assertIsNone(coordinator.request(RefreshReason.PERIODIC))
        self.assertFalse(coordinator.pending)

    def test_queues_requests_during_mutation(self) -> None:
        coordinator = RefreshCoordinator()
        coordinator.begin_mutation()

        self.assertIsNone(coordinator.request(RefreshReason.MANUAL))
        self.assertTrue(coordinator.pending)
        coordinator.end_mutation()
        self.assertTrue(coordinator.take_pending())

    def test_rejects_stale_completion(self) -> None:
        coordinator = RefreshCoordinator()
        generation = coordinator.request(RefreshReason.INITIAL)

        self.assertFalse(coordinator.complete(0))
        self.assertTrue(coordinator.is_current(generation or 0))


class TestInitialLoadingFrame(unittest.IsolatedAsyncioTestCase):
    async def test_keeps_topics_frame_visible_while_table_loads(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        service = MagicMock()
        configure_admin_service(service, {})

        async def metadata() -> dict[str, Topic]:
            started.set()
            await release.wait()
            return {}

        service.metadata = AsyncMock(side_effect=metadata)
        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                try:
                    await started.wait()
                    await pilot.pause()
                    frame = app.query_one("#topics-frame", TableFrame)
                    table = app.query_one("#topics-table", DataTable)

                    self.assertTrue(table.loading)
                    self.assertFalse(frame.loading)
                    self.assertIn("Topics", frame.border_title)
                    self.assertNotEqual("", frame.styles.border_top[0])
                    self.assertEqual("", table.styles.border_top[0])
                finally:
                    release.set()
                await app.workers.wait_for_complete()

    async def test_topics_table_keeps_focus_after_slow_first_load(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        service = MagicMock()
        configure_admin_service(service, {})

        async def metadata() -> dict[str, Topic]:
            started.set()
            await release.wait()
            return {"orders": Topic(name="orders")}

        service.metadata = AsyncMock(side_effect=metadata)
        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await started.wait()
                await pilot.pause()
                release.set()
                await app.workers.wait_for_complete()
                await pilot.pause()

                self.assertIs(app.query_one("#topics-table", DataTable), app.focused)

    async def test_shows_only_truncated_topic_name_in_table_tooltip(self) -> None:
        long_topic = Topic(name="example-streamlet.sl.example-streamlet")
        short_topic = Topic(name="orders")
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(
                topic_service.return_value,
                {long_topic.name: long_topic, short_topic.name: short_topic},
            )
            app = KaskadeAdmin({})

            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                table = app.query_one(TopicDataTable)

                table.hover_coordinate = Coordinate(0, 0)
                await pilot.pause()
                self.assertEqual(long_topic.name, table.tooltip)

                table.hover_coordinate = Coordinate(0, 1)
                await pilot.pause()
                self.assertIsNone(table.tooltip)

                table.hover_coordinate = Coordinate(1, 0)
                await pilot.pause()
                self.assertIsNone(table.tooltip)


class TestCreateTopic(unittest.IsolatedAsyncioTestCase):
    async def test_f2_creates_topic_from_an_input(self) -> None:
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})
            results: list[CreateTopicCommand | None] = []

            async with app.run_test() as pilot:
                app.push_screen(CreateTopicScreen(), results.append)
                await pilot.pause()
                app.screen.query_one("#name", Input).value = "orders"

                await pilot.press("f2")

                self.assertEqual("orders", results[0].name)

    async def test_ctrl_shift_s_creates_topic_from_an_input(self) -> None:
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})
            results: list[CreateTopicCommand | None] = []

            async with app.run_test() as pilot:
                app.push_screen(CreateTopicScreen(), results.append)
                await pilot.pause()
                app.screen.query_one("#name", Input).value = "orders"

                await pilot.press("ctrl+shift+s")

                self.assertEqual("orders", results[0].name)

    async def test_uses_broker_defaults_for_advanced_replication_settings(self) -> None:
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})
            results: list[CreateTopicCommand | None] = []

            async with app.run_test() as pilot:
                app.push_screen(CreateTopicScreen(), results.append)
                await pilot.pause()

                advanced = app.screen.query_one("#advanced-topic-config", Collapsible)
                self.assertTrue(advanced.collapsed)
                self.assertEqual("", app.screen.query_one("#replicas", Input).value)
                self.assertEqual("", app.screen.query_one("#min_insync_replicas", Input).value)

                app.screen.query_one("#name", Input).value = "orders"
                await pilot.press("ctrl+s")

                self.assertEqual(1, len(results))
                self.assertIsNone(results[0].replicas)
                self.assertIsNone(results[0].min_insync_replicas)

    async def test_keeps_invalid_topic_configuration_open(self) -> None:
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})
            results: list[CreateTopicCommand | None] = []

            async with app.run_test() as pilot:
                app.push_screen(CreateTopicScreen(), results.append)
                await pilot.pause()

                await pilot.press("ctrl+s")

                self.assertIsInstance(app.screen, CreateTopicScreen)
                self.assertEqual([], results)
                self.assertTrue(app.screen.query_one("#name", Input).has_class("-invalid"))

                app.screen.query_one("#name", Input).value = "orders"
                app.screen.query_one("#replicas", Input).value = "1"
                app.screen.query_one("#min_insync_replicas", Input).value = "2"
                await pilot.press("ctrl+s")

                self.assertIsInstance(app.screen, CreateTopicScreen)
                self.assertEqual([], results)
                self.assertTrue(
                    app.screen.query_one("#min_insync_replicas", Input).has_class("-invalid")
                )

                app.screen.query_one("#min_insync_replicas", Input).value = "1"
                await pilot.press("ctrl+s")

                self.assertEqual(1, len(results))
                self.assertEqual("orders", results[0].name)

    async def test_stops_loading_when_kafka_rejects_topic(self) -> None:
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            topic_service.return_value.create.side_effect = KafkaException("invalid topic")
            app = KaskadeAdmin({})

            async with app.run_test() as pilot:
                await pilot.pause()
                topics = app.query_one(ListTopics)
                table = app.query_one("#topics-table", DataTable)

                worker = topics.create_topic(
                    CreateTopicCommand("orders", 1, 1, 1, "delete", 604800000)
                )
                await worker.wait()
                await pilot.pause()

                self.assertFalse(table.loading)


class TestUpdateTopic(unittest.IsolatedAsyncioTestCase):
    async def test_ctrl_shift_s_saves_and_applies_topic_changes(self) -> None:
        app = KaskadeAdmin({})
        results: list[UpdateTopicCommand | None] = []

        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            async with app.run_test() as pilot:
                app.push_screen(edit_topic_screen(), results.append)
                await pilot.pause()
                app.screen.query_one("#retention", Input).value = "2000"

                await save_and_apply(pilot, "ctrl+shift+s")

                change = ConfigChange(RETENTION_MS_CONFIG, "1000", "2000")
                self.assertEqual([UpdateTopicCommand(configs=(change,))], results)

    async def test_closes_without_review_when_nothing_changed(self) -> None:
        for cleanup_policy in ("delete", "compact,delete"):
            with (
                self.subTest(cleanup_policy=cleanup_policy),
                patch("kaskade.admin.app.TopicService") as topic_service,
            ):
                configure_admin_service(topic_service.return_value, {})
                app = KaskadeAdmin({})
                app.notify = MagicMock()
                results: list[UpdateTopicCommand | None] = []
                async with app.run_test() as pilot:
                    app.push_screen(
                        edit_topic_screen(cleanup_policy=cleanup_policy), results.append
                    )
                    await pilot.pause()
                    advanced = app.screen.query_one("#advanced-topic-config", Collapsible)
                    self.assertTrue(advanced.collapsed)
                    self.assertEqual("2", app.screen.query_one("#min_insync_replicas", Input).value)

                    await pilot.press("ctrl+s")
                    await pilot.pause()

                    self.assertEqual([None], results)
                    self.assertNotIsInstance(app.screen, ReviewTopicChangesScreen)
                    app.notify.assert_called_once_with(
                        "No changes to topic 'orders'",
                        title="No Changes",
                        severity="information",
                    )

    async def test_includes_only_changed_topic_configuration_in_command(self) -> None:
        cases = (
            ("min_insync", ConfigChange(MIN_INSYNC_REPLICAS_CONFIG, "2", "1")),
            ("cleanup", ConfigChange(CLEANUP_POLICY_CONFIG, "delete", "compact")),
            ("retention", ConfigChange(RETENTION_MS_CONFIG, "1000", "2000")),
        )

        for setting, expected in cases:
            with self.subTest(setting=setting):
                app = KaskadeAdmin({})
                results: list[UpdateTopicCommand | None] = []
                with patch("kaskade.admin.app.TopicService") as topic_service:
                    configure_admin_service(topic_service.return_value, {})
                    async with app.run_test() as pilot:
                        app.push_screen(edit_topic_screen(), results.append)
                        await pilot.pause()

                        if setting == "min_insync":
                            app.screen.query_one("#min_insync_replicas", Input).value = "1"
                        elif setting == "cleanup":
                            cleanup = app.screen.query_one("#cleanup", RadioSet)
                            cleanup.query(RadioButton)[1].value = True
                        else:
                            app.screen.query_one("#retention", Input).value = "02000"

                        await save_and_apply(pilot)

                        self.assertEqual([UpdateTopicCommand(configs=(expected,))], results)

    async def test_clearing_an_overridden_value_resets_it(self) -> None:
        app = KaskadeAdmin({})
        results: list[UpdateTopicCommand | None] = []

        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            async with app.run_test() as pilot:
                app.push_screen(edit_topic_screen(), results.append)
                await pilot.pause()
                app.screen.query_one("#min_insync_replicas", Input).value = ""

                await save_and_apply(pilot)

                self.assertEqual(
                    [
                        UpdateTopicCommand(
                            configs=(ConfigChange(MIN_INSYNC_REPLICAS_CONFIG, "2", None),)
                        )
                    ],
                    results,
                )

    async def test_clearing_an_inherited_value_changes_nothing(self) -> None:
        app = KaskadeAdmin({})
        results: list[UpdateTopicCommand | None] = []

        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            async with app.run_test() as pilot:
                app.push_screen(edit_topic_screen(retention_overridden=False), results.append)
                await pilot.pause()
                app.screen.query_one("#retention", Input).value = ""

                await pilot.press("ctrl+s")
                await pilot.pause()

                self.assertEqual([None], results)

    async def test_review_lists_each_change_with_its_current_and_new_value(self) -> None:
        app = KaskadeAdmin({})

        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            async with app.run_test() as pilot:
                app.push_screen(edit_topic_screen())
                await pilot.pause()
                app.screen.query_one("#partitions", Input).value = "5"
                app.screen.query_one("#retention", Input).value = "2000"
                app.screen.query_one("#min_insync_replicas", Input).value = ""

                await pilot.press("ctrl+s")
                await pilot.pause()

                self.assertIsInstance(app.screen, ReviewTopicChangesScreen)
                table = app.screen.query_one("#topic-changes", DataTable)
                self.assertEqual(
                    [
                        ["Partitions", "Increase", "3", "5"],
                        [MIN_INSYNC_REPLICAS_CONFIG, "Reset", "2", "Cluster default"],
                        [RETENTION_MS_CONFIG, "Set", "1000", "2000"],
                    ],
                    [table.get_row_at(index) for index in range(table.row_count)],
                )

    async def test_back_from_review_returns_to_the_edits_without_applying(self) -> None:
        app = KaskadeAdmin({})
        results: list[UpdateTopicCommand | None] = []

        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            async with app.run_test() as pilot:
                app.push_screen(edit_topic_screen(), results.append)
                await pilot.pause()
                app.screen.query_one("#retention", Input).value = "2000"

                await pilot.press("ctrl+s")
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()

                self.assertIsInstance(app.screen, EditTopicScreen)
                self.assertEqual("2000", app.screen.query_one("#retention", Input).value)
                self.assertEqual([], results)

                await pilot.press("escape")
                await pilot.pause()

                self.assertEqual([None], results)
                topic_service.return_value.edit.assert_not_called()

    async def test_reads_cleanup_policy_from_the_button_not_its_label(self) -> None:
        screens: tuple[CreateTopicScreen | EditTopicScreen, ...] = (
            CreateTopicScreen(),
            edit_topic_screen(),
        )
        for screen in screens:
            with self.subTest(screen=type(screen).__name__):
                app = KaskadeAdmin({})
                results: list[Any] = []
                with patch("kaskade.admin.app.TopicService") as topic_service:
                    configure_admin_service(topic_service.return_value, {})
                    async with app.run_test() as pilot:
                        app.push_screen(screen, results.append)
                        await pilot.pause()
                        if isinstance(screen, CreateTopicScreen):
                            app.screen.query_one("#name", Input).value = "orders"
                        compact = app.screen.query(RadioButton)[1]
                        compact.label = "Compacted"
                        compact.value = True

                        if isinstance(screen, CreateTopicScreen):
                            await pilot.press("ctrl+s")
                            self.assertEqual("compact", results[0].cleanup_policy)
                        else:
                            await save_and_apply(pilot)
                            self.assertEqual("compact", results[0].configs[0].value)

    async def test_cleanup_cursor_starts_on_the_configured_policy(self) -> None:
        for policy, selected in (("compact", "compact"), ("delete", "delete"), ("", "delete")):
            with (
                self.subTest(policy=policy),
                patch("kaskade.admin.app.TopicService") as topic_service,
            ):
                configure_admin_service(topic_service.return_value, {})
                app = KaskadeAdmin({})
                async with app.run_test() as pilot:
                    app.push_screen(edit_topic_screen(cleanup_policy=policy))
                    await pilot.pause()

                    buttons = list(app.screen.query("#cleanup RadioButton").results(RadioButton))
                    highlighted = [
                        str(button.label) for button in buttons if button.has_class("-selected")
                    ]
                    self.assertEqual([selected], highlighted)

    async def test_expands_advanced_when_min_insync_is_invalid(self) -> None:
        app = KaskadeAdmin({})
        results: list[UpdateTopicCommand | None] = []

        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            async with app.run_test() as pilot:
                app.push_screen(edit_topic_screen(), results.append)
                await pilot.pause()
                app.screen.query_one("#min_insync_replicas", Input).value = "0"

                await pilot.press("ctrl+s")

                self.assertEqual([], results)
                self.assertFalse(
                    app.screen.query_one("#advanced-topic-config", Collapsible).collapsed
                )

    async def test_allows_missing_min_insync_to_remain_unchanged(self) -> None:
        app = KaskadeAdmin({})
        results: list[UpdateTopicCommand | None] = []

        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            async with app.run_test() as pilot:
                app.push_screen(edit_topic_screen(min_insync_replicas=""), results.append)
                await pilot.pause()

                await pilot.press("ctrl+s")

                self.assertEqual([None], results)

    async def test_rejects_partition_decreases_before_mutating(self) -> None:
        app = KaskadeAdmin({})
        results: list[UpdateTopicCommand | None] = []

        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            async with app.run_test() as pilot:
                app.push_screen(edit_topic_screen(min_insync_replicas="1"), results.append)
                await pilot.pause()
                app.screen.query_one("#partitions", Input).value = "2"

                await pilot.press("ctrl+s")

                self.assertIsInstance(app.screen, EditTopicScreen)
                self.assertEqual([], results)

    async def test_sends_only_changed_topic_configuration(self) -> None:
        topic = Topic(name="orders", partitions=[Partition(id=0, topic="orders")])
        service = MagicMock()
        configure_admin_service(service, {topic.name: topic})
        changes = (ConfigChange(MIN_INSYNC_REPLICAS_CONFIG, "1", "2"),)

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            app.notify = MagicMock()
            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                topics = app.query_one(ListTopics)
                worker = topics.update_topic(topic, UpdateTopicCommand(configs=changes))
                await worker.wait()
                await pilot.pause()

                service.add_partitions.assert_not_called()
                service.edit.assert_called_once_with("orders", changes)
                app.notify.assert_called_with(
                    "Updated topic 'orders'", title="Topic Updated", severity="information"
                )

    async def test_partition_only_update_skips_topic_config_edit(self) -> None:
        topic = Topic(name="orders", partitions=[Partition(id=0, topic="orders")])
        service = MagicMock()
        configure_admin_service(service, {topic.name: topic})

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            app.notify = MagicMock()
            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                topics = app.query_one(ListTopics)
                worker = topics.update_topic(topic, UpdateTopicCommand(partitions=2))
                await worker.wait()
                await pilot.pause()

                service.add_partitions.assert_called_once_with("orders", 2)
                service.edit.assert_not_called()

    async def test_refreshes_after_partial_topic_update(self) -> None:
        topic = Topic(name="orders", partitions=[Partition(id=0, topic="orders")])
        service = MagicMock()
        configure_admin_service(service, {topic.name: topic})
        service.edit.side_effect = KafkaException("config rejected")

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            app.notify = MagicMock()
            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                topics = app.query_one(ListTopics)
                with patch.object(topics, "set_timer") as set_timer:
                    worker = topics.update_topic(
                        topic,
                        UpdateTopicCommand(
                            partitions=2,
                            configs=(ConfigChange(RETENTION_MS_CONFIG, "1000", None),),
                        ),
                    )
                    await worker.wait()
                    await pilot.pause()

                service.add_partitions.assert_called_once_with("orders", 2)
                set_timer.assert_called_once()
                self.assertTrue(
                    any(
                        call.kwargs.get("title") == "Topic Partially Updated"
                        for call in app.notify.call_args_list
                    )
                )


class TestDescribeTopic(unittest.IsolatedAsyncioTestCase):
    async def test_displays_partition_offsets_and_lag_for_each_group_partition(self) -> None:
        topic = Topic(
            name="orders",
            partitions=[Partition(id=0, leader=1, low=10, high=100)],
            groups=[
                Group(id="shipping", partitions=[GroupPartition(id=0, offset=75, high=100)]),
                Group(id="billing", partitions=[GroupPartition(id=0, offset=100, high=100)]),
            ],
            records_state=MetricState.READY,
            groups_state=MetricState.READY,
        )
        for theme in ("eva01-berserk", "eva01", "textual-light", "ansi-light"):
            with self.subTest(theme=theme), patch("kaskade.admin.app.TopicService") as service:
                configure_admin_service(service.return_value, {})
                app = KaskadeAdmin({})
                app.theme = theme
                async with app.run_test(size=(100, 30)) as pilot:
                    app.push_screen(DescribeTopicScreen(topic, ()))
                    await pilot.pause()
                    partitions = app.screen.query_one("#partitions-table", DataTable)
                    self.assertEqual(
                        ["ID", "Leader", "Earliest", "End", "Records", "ISRs", "Replicas"],
                        [column.label.plain for column in partitions.ordered_columns],
                    )
                    self.assertEqual(
                        ["0", "1", "10", "100", "90", "[]", "[]"], partitions.get_row_at(0)
                    )
                    await pilot.press("l", "l", "l")
                    self.assertEqual("group-offsets", app.screen.query_one(TabbedContent).active)
                    offsets = app.screen.query_one("#group-offsets-table", DataTable)
                    self.assertEqual(
                        ["Group", "Partition", "Committed", "End", "Lag"],
                        [column.label.plain for column in offsets.ordered_columns],
                    )
                    self.assertEqual(["shipping", "0", "75", "100", "25"], offsets.get_row_at(0))
                    self.assertEqual(["billing", "0", "100", "100", "0"], offsets.get_row_at(1))
                    self.assertFalse(offsets.show_horizontal_scrollbar)
                    await pilot.resize_terminal(60, 30)
                    await pilot.pause()
                    self.assertGreater(offsets.content_region.height, 0)

    async def test_prioritizes_identity_columns_and_reveals_truncated_cells(self) -> None:
        group_id = "apicurio-c994055a-very-long-consumer-group-identifier"
        coordinator_node = Node(
            id=390923,
            host="broker-with-a-long-network-name.example",
            port=39092,
        )
        coordinator = str(coordinator_node)
        assignment = list(range(20))
        topic = Topic(
            name="orders",
            groups=[
                Group(
                    id=group_id,
                    coordinator=coordinator_node,
                    state="Stable",
                    partition_assignor="range",
                    members=[
                        GroupMember(
                            id="long-member-identifier-for-the-consumer",
                            client_id="long-client-identifier-for-the-consumer",
                            group=group_id,
                            host="host-with-a-long-network-name",
                            assignment=assignment,
                        )
                    ],
                )
            ],
            records_state=MetricState.READY,
            groups_state=MetricState.READY,
        )

        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})
            async with app.run_test(size=(80, 30)) as pilot:
                app.push_screen(DescribeTopicScreen(topic, ()))
                await pilot.pause()
                tabs = app.screen.query_one("#topic-details-tabs")

                tabs.active = "groups"
                await pilot.pause()
                groups = app.screen.query_one("#groups-table", DataTable)
                self.assertGreater(
                    groups.ordered_columns[0].width,
                    groups.ordered_columns[2].width,
                )
                self.assertGreater(
                    groups.ordered_columns[1].width,
                    groups.ordered_columns[2].width,
                )
                groups.hover_coordinate = Coordinate(0, 0)
                await pilot.pause()
                self.assertEqual(group_id, groups.tooltip)
                groups.hover_coordinate = Coordinate(0, 1)
                await pilot.pause()
                self.assertEqual(coordinator, groups.tooltip)
                groups.hover_coordinate = Coordinate(0, 6)
                await pilot.pause()
                self.assertIsNone(groups.tooltip)

                app.screen.query_one("Tabs").focus()
                await pilot.press("l", "l")
                await pilot.pause()
                members = app.screen.query_one("#group-members-table", DataTable)
                self.assertLess(
                    members.ordered_columns[4].width,
                    members.ordered_columns[2].width,
                )
                members.hover_coordinate = Coordinate(0, 4)
                await pilot.pause()
                self.assertEqual(str(assignment), members.tooltip)

    async def test_displays_topic_summary_metadata(self) -> None:
        topic = Topic(
            name="orders",
            partitions=[
                Partition(id=0, replicas=[1, 2, 3], isrs=[1, 2], low=5, high=20),
                Partition(id=1, replicas=[1, 2, 3], isrs=[1, 2], low=0, high=10),
            ],
            groups=[
                Group(
                    id="shipping",
                    members=[GroupMember(id="member-1"), GroupMember(id="member-2")],
                    partitions=[
                        GroupPartition(id=0, offset=15, low=5, high=20),
                        GroupPartition(id=1, offset=8, low=0, high=10),
                    ],
                )
            ],
            records_state=MetricState.READY,
            groups_state=MetricState.READY,
        )

        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                app.push_screen(DescribeTopicScreen(topic, ()))
                await pilot.pause()

                self.assertEqual(
                    "[primary]Topic Details[/primary] [[primary]orders[/primary]]",
                    app.screen.query_one(".topic-details").border_title,
                )
                self.assertEqual(
                    [
                        "PARTIT…\n2",
                        "REPLICAS\n3",
                        "IN SYNC\n2",
                        "GROUPS\n1",
                        "MEMBERS\n2",
                        "RECORDS\n≈25",
                        "LAG\n≈7",
                    ],
                    [
                        cell.render().plain
                        for cell in app.screen.query(".topic-metadata-cell").results(Static)
                    ],
                )
                self.assertEqual(
                    "Partitions",
                    app.screen.query_one("#topic-partitions", Static).tooltip,
                )

    async def test_loads_configurations_before_opening_topic_details(self) -> None:
        topic = Topic(name="orders")
        configurations = (TopicConfiguration("cleanup.policy", "compact"),)
        service = MagicMock()
        configure_admin_service(service, {topic.name: topic})
        service.describe_configs.return_value = configurations

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                await pilot.pause()

                await pilot.press("d")
                await app.workers.wait_for_complete()
                await pilot.pause()

                self.assertIsInstance(app.screen, DescribeTopicScreen)
                self.assertEqual(configurations, app.screen.configurations)
                service.describe_configs.assert_called_once_with("orders")
                self.assertFalse(app.query_one("#topics-table", DataTable).loading)

    async def test_fast_edit_opens_without_flashing_the_table_loading(self) -> None:
        topic = Topic(name="orders")
        service = MagicMock()
        configure_admin_service(service, {topic.name: topic})
        service.describe_configs.return_value = ()

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                await pilot.pause()
                table = app.query_one("#topics-table", DataTable)
                loading_states: list[bool] = []
                app.watch(table, "loading", loading_states.append, init=False)

                await pilot.press("e")
                await app.workers.wait_for_complete()
                await pilot.pause()

                self.assertIsInstance(app.screen, EditTopicScreen)
                self.assertNotIn(True, loading_states)

    async def test_slow_details_show_the_table_loading(self) -> None:
        topic = Topic(name="orders")
        service = MagicMock()
        configure_admin_service(service, {topic.name: topic})
        release = asyncio.Event()
        loop = asyncio.get_running_loop()

        def slow_describe_configs(_: str) -> dict[str, str]:
            asyncio.run_coroutine_threadsafe(release.wait(), loop).result()
            return {}

        service.describe_configs.side_effect = slow_describe_configs

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                await pilot.pause()
                table = app.query_one("#topics-table", DataTable)

                await pilot.press("d")
                await pilot.pause(DETAILS_LOADING_DELAY + 0.2)
                self.assertTrue(table.loading)

                release.set()
                await app.workers.wait_for_complete()
                await pilot.pause()

                self.assertIsInstance(app.screen, DescribeTopicScreen)
                self.assertFalse(table.loading)

    async def test_reports_configuration_failure_without_opening_topic_details(self) -> None:
        topic = Topic(name="orders")
        service = MagicMock()
        configure_admin_service(service, {topic.name: topic})
        service.describe_configs.side_effect = KafkaException("configs unavailable")

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            app.notify = MagicMock()
            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                await pilot.pause()

                await pilot.press("d")
                await app.workers.wait_for_complete()
                await pilot.pause()

                self.assertNotIsInstance(app.screen, DescribeTopicScreen)
                self.assertFalse(app.query_one("#topics-table", DataTable).loading)
                self.assertTrue(
                    any(
                        call.kwargs.get("title") == "Kafka Error"
                        for call in app.notify.call_args_list
                    )
                )


class TestTopicCopyActions(unittest.IsolatedAsyncioTestCase):
    async def test_y_copies_topic_from_table_and_details(self) -> None:
        topic = Topic(name="orders")
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {topic.name: topic})
            app = KaskadeAdmin({})
            app.notify = MagicMock()

            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                await pilot.pause()
                topics = app.query_one(ListTopics)

                self.assertTrue(topics.check_action("copy_topic", ()))
                self.assertIn(
                    "Copy Topic",
                    {command.title for command in app.get_system_commands(app.screen)},
                )

                await pilot.press("y")

                self.assertEqual("orders", app.clipboard)
                app.notify.assert_called_once_with(
                    "Copied topic name to clipboard",
                    title="Copied",
                )

                app.push_screen(
                    DescribeTopicScreen(
                        topic,
                        (
                            TopicConfiguration("retention.ms", "604800000"),
                            TopicConfiguration("cleanup.policy", "compact"),
                        ),
                    )
                )
                await pilot.pause()
                app.copy_to_clipboard("")
                app.notify.reset_mock()

                await pilot.press("y")

                self.assertEqual("orders", app.clipboard)
                app.notify.assert_called_once_with(
                    "Copied topic name to clipboard",
                    title="Copied",
                )

                await pilot.press("l")
                configurations = app.screen.query_one("#configurations-table", DataTable)
                configurations.move_cursor(row=1)
                app.copy_to_clipboard("")
                app.notify.reset_mock()

                await pilot.press("y")

                self.assertEqual("retention.ms=604800000", app.clipboard)
                app.notify.assert_called_once_with(
                    "Copied configuration to clipboard",
                    title="Copied",
                )

    async def test_copy_is_disabled_without_a_topic(self) -> None:
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})
            app.notify = MagicMock()

            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                await pilot.pause()
                topics = app.query_one(ListTopics)

                self.assertFalse(topics.check_action("copy_topic", ()))
                await pilot.press("y")

                self.assertEqual("", app.clipboard)
                app.notify.assert_not_called()


class TestReadOnlyMode(unittest.IsolatedAsyncioTestCase):
    MUTATIONS = (
        ("new", "n", "Create"),
        ("edit", "e", "Edit"),
        ("delete", "ctrl+d", "Delete"),
    )

    async def test_hides_and_refuses_every_mutating_action(self) -> None:
        topic = Topic(name="orders")
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {topic.name: topic})
            app = KaskadeAdmin({}, settings=replace(load_settings(), admin_read_only=True))

            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                await pilot.pause()
                topics = app.query_one(ListTopics)
                commands = {command.title for command in app.get_system_commands(app.screen)}
                help_entries = {entry.description for entry in contextual_help(app.screen)[1]}

                self.assertIn(
                    "Read Only", app.query_one("#topics-frame", TableFrame).border_subtitle
                )
                for action, key, description in self.MUTATIONS:
                    with self.subTest(action=action):
                        self.assertFalse(topics.check_action(action, ()))
                        self.assertNotIn(description, commands)
                        self.assertNotIn(description, help_entries)

                        await pilot.press(key)
                        await pilot.pause()

                        self.assertIs(app.screen, app.screen_stack[0])

    async def test_read_write_mode_keeps_mutating_actions(self) -> None:
        topic = Topic(name="orders")
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {topic.name: topic})
            app = KaskadeAdmin({})

            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                await pilot.pause()
                topics = app.query_one(ListTopics)

                self.assertNotIn(
                    "Read Only", app.query_one("#topics-frame", TableFrame).border_subtitle
                )
                for action, _, _ in self.MUTATIONS:
                    with self.subTest(action=action):
                        self.assertTrue(topics.check_action(action, ()))


class TestAdminRefresh(unittest.IsolatedAsyncioTestCase):
    async def test_cancels_and_awaits_pending_stage_tasks(self) -> None:
        gate = asyncio.Event()

        async def wait_forever() -> None:
            await gate.wait()

        tasks = [asyncio.create_task(wait_forever()), asyncio.create_task(wait_forever())]

        await ListTopics._cancel_stage_tasks(tasks)

        self.assertTrue(all(task.done() and task.cancelled() for task in tasks))

    async def test_shutdown_cancels_active_refresh_without_updating_detached_widgets(self) -> None:
        enrichment_gate = asyncio.Event()
        topic = Topic(name="orders", partitions=[Partition(id=0)])
        service = MagicMock()
        service.metadata = AsyncMock(return_value={"orders": topic})

        async def wait_for_enrichment() -> EnrichmentResult:
            await enrichment_gate.wait()
            return EnrichmentResult()

        service.enrich_offsets.side_effect = lambda topics: wait_for_enrichment()
        service.load_groups.side_effect = wait_for_enrichment

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await pilot.pause()
                self.assertEqual(1, len(app.query_one(DataTable).rows))

    async def test_command_line_interval_overrides_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "settings.yaml"
            config_path.write_text(
                "admin:\n  refresh-interval: 60\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {SETTINGS_ENV_VAR: str(config_path)}):
                app = KaskadeAdmin(
                    {}, settings=replace(load_settings(), admin_refresh_interval_seconds=10)
                )

                self.assertEqual(10, app.auto_refresh_interval)

    async def test_can_disable_auto_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "settings.yaml"
            config_path.write_text(
                "admin:\n  refresh-interval: 0\n",
                encoding="utf-8",
            )
            with (
                patch.dict(os.environ, {SETTINGS_ENV_VAR: str(config_path)}),
                patch("kaskade.admin.app.TopicService") as topic_service,
            ):
                configure_admin_service(topic_service.return_value, {})
                app = KaskadeAdmin({})
                async with app.run_test() as pilot:
                    await app.workers.wait_for_complete()
                    await pilot.pause()

                    self.assertEqual(0, app.auto_refresh_interval)
                    self.assertIsNone(app._periodic_refresh_timer)
                    self.assertIn(
                        "Auto Off",
                        app.query_one("#topics-frame", TableFrame).border_subtitle,
                    )

    async def test_renders_metadata_before_metrics_finish(self) -> None:
        offsets_gate = asyncio.Event()
        groups_gate = asyncio.Event()
        topic = Topic(
            name="orders",
            partitions=[Partition(id=0, replicas=[0, 1], isrs=[0, 1])],
        )
        service = MagicMock()
        service.metadata = AsyncMock(return_value={"orders": topic})

        async def enrich_offsets(topics: dict[str, Topic]) -> EnrichmentResult:
            await offsets_gate.wait()
            topics["orders"].partitions[0].high = 10
            topics["orders"].records_state = MetricState.READY
            return EnrichmentResult()

        async def load_groups() -> GroupSnapshot:
            await groups_gate.wait()
            return GroupSnapshot()

        service.enrich_offsets.side_effect = enrich_offsets
        service.load_groups.side_effect = load_groups
        service.apply_groups.side_effect = lambda topics, snapshot: EnrichmentResult()

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await pilot.pause()
                table = app.query_one("#topics-table", DataTable)

                self.assertEqual(1, len(table.rows))
                self.assertEqual("…", table.get_cell("orders", "records"))
                offsets_gate.set()
                await pilot.pause()
                self.assertEqual("≈10", table.get_cell("orders", "records"))
                groups_gate.set()
                await app.workers.wait_for_complete()

    async def test_periodic_refresh_does_not_overlap_and_resumes_after_modal(self) -> None:
        gate = asyncio.Event()
        service = MagicMock()

        async def metadata() -> dict[str, Topic]:
            await gate.wait()
            return {}

        service.metadata.side_effect = metadata
        service.enrich_offsets = AsyncMock(return_value=EnrichmentResult())
        service.load_groups = AsyncMock(return_value=GroupSnapshot())
        service.apply_groups.return_value = EnrichmentResult()

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await pilot.pause()
                app._request_periodic_refresh()
                self.assertEqual(1, service.metadata.call_count)
                gate.set()
                await app.workers.wait_for_complete()

                service.metadata.reset_mock()
                app.push_screen(FilterTopicsScreen())
                await pilot.pause()
                app._request_periodic_refresh()
                self.assertEqual(0, service.metadata.call_count)

                app.pop_screen()
                await asyncio.sleep(0.2)
                await pilot.pause()
                self.assertEqual(1, service.metadata.call_count)

    async def test_manual_refreshes_coalesce_without_overlapping(self) -> None:
        first_refresh_gate = asyncio.Event()
        active_calls = 0
        max_active_calls = 0
        service = MagicMock()

        async def metadata() -> dict[str, Topic]:
            nonlocal active_calls, max_active_calls
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
            if service.metadata.call_count == 1:
                await first_refresh_gate.wait()
            active_calls -= 1
            return {}

        service.metadata.side_effect = metadata
        service.enrich_offsets = AsyncMock(return_value=EnrichmentResult())
        service.load_groups = AsyncMock(return_value=GroupSnapshot())
        service.apply_groups.return_value = EnrichmentResult()

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await pilot.pause()
                topics = app.query_one(ListTopics)
                topics.request_refresh(RefreshReason.MANUAL)
                topics.request_refresh(RefreshReason.MANUAL)

                self.assertEqual(1, service.metadata.call_count)

                async def pending_refresh_started() -> None:
                    # The coalesced refresh starts after the next screen refresh.
                    while service.metadata.call_count < 2:
                        await pilot.pause()

                first_refresh_gate.set()
                await asyncio.wait_for(pending_refresh_started(), timeout=5)
                await app.workers.wait_for_complete()

                self.assertEqual(2, service.metadata.call_count)
                self.assertEqual(1, max_active_calls)

    async def test_consolidates_partial_stage_failures(self) -> None:
        topic = Topic(name="orders", partitions=[Partition(id=0)])
        service = MagicMock()
        service.metadata = AsyncMock(return_value={"orders": topic})
        service.enrich_offsets = AsyncMock(
            return_value=EnrichmentResult((RuntimeError("offsets"),))
        )
        service.load_groups = AsyncMock(
            return_value=GroupSnapshot(errors=(RuntimeError("groups"),))
        )
        service.apply_groups.return_value = EnrichmentResult((RuntimeError("groups"),))

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            with patch.object(app, "notify") as notify:
                async with app.run_test():
                    await app.workers.wait_for_complete()

            partial_notifications = [
                call
                for call in notify.call_args_list
                if call.kwargs.get("title") == "Partial Refresh"
            ]
            self.assertEqual(1, len(partial_notifications))
            message = partial_notifications[0].args[0]
            self.assertIn("record metrics", message)
            self.assertIn("consumer-group metrics", message)
            self.assertFalse(message.endswith("."))

    async def test_programming_errors_fail_refresh_instead_of_partial_metrics(self) -> None:
        service = MagicMock()
        service.metadata = AsyncMock(
            return_value={"orders": Topic(name="orders", partitions=[Partition(id=0)])}
        )
        service.enrich_offsets = AsyncMock(side_effect=TypeError("bad argument"))
        service.load_groups = AsyncMock(return_value=GroupSnapshot())
        service.apply_groups.return_value = EnrichmentResult()

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            with (
                patch.object(app, "notify") as notify,
                redirect_stderr(StringIO()),
                self.assertLogs("kaskade", level="ERROR") as logs,
                self.assertRaises(WorkerFailed) as failure,
            ):
                async with app.run_test():
                    await app.workers.wait_for_complete()

        self.assertIsInstance(failure.exception.error, TypeError)
        self.assertIn("admin refresh failed unexpectedly", logs.output[0])
        self.assertIsNotNone(logs.records[0].exc_info)
        self.assertNotIn(
            "Partial Refresh", [call.kwargs.get("title") for call in notify.call_args_list]
        )

    async def test_metadata_failure_keeps_previous_snapshot(self) -> None:
        topic = Topic(
            name="orders",
            partitions=[Partition(id=0, high=10)],
            records_state=MetricState.READY,
            groups_state=MetricState.READY,
        )
        service = MagicMock()
        service.metadata = AsyncMock(
            side_effect=[{"orders": topic}, KafkaException("metadata unavailable")]
        )
        service.enrich_offsets = AsyncMock(return_value=EnrichmentResult())
        service.load_groups = AsyncMock(return_value=GroupSnapshot())
        service.apply_groups.return_value = EnrichmentResult()

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                table = app.query_one(DataTable)
                topics = app.query_one(ListTopics)

                topics.request_refresh(RefreshReason.MANUAL)
                await app.workers.wait_for_complete()
                await pilot.pause()

                self.assertEqual("≈10", table.get_cell("orders", "records"))
                self.assertIs(topic, topics.topics["orders"])

    async def test_refresh_preserves_filter_selection_and_completed_metrics(self) -> None:
        previous = Topic(
            name="payments",
            partitions=[Partition(id=0, high=25)],
            records_state=MetricState.READY,
            groups_state=MetricState.READY,
        )
        refreshed = Topic(name="payments", partitions=[Partition(id=0)])
        service = MagicMock()
        service.metadata = AsyncMock(
            side_effect=[
                {"orders": Topic(name="orders"), "payments": previous},
                {"payments": refreshed},
            ]
        )
        service.enrich_offsets = AsyncMock(return_value=EnrichmentResult())
        service.load_groups = AsyncMock(return_value=GroupSnapshot())
        service.apply_groups.return_value = EnrichmentResult()

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                topics = app.query_one(ListTopics)
                topics.current_filter = "payments"
                topics.current_topic = previous
                topics.fill_table()

                topics.request_refresh(RefreshReason.MANUAL)
                await app.workers.wait_for_complete()
                await pilot.pause()

                table = app.query_one(DataTable)
                self.assertEqual("payments", topics.current_filter)
                self.assertEqual("payments", topics.current_topic.name)
                self.assertEqual("≈25", table.get_cell("payments", "records"))


def topic_with_groups() -> Topic:
    """A two-partition topic consumed by 'billing' on both partitions."""
    return Topic(
        name="orders",
        partitions=[Partition(id=0, topic="orders"), Partition(id=1, topic="orders")],
        groups=[
            Group(
                id="billing",
                partitions=[
                    GroupPartition(id=0, offset=5, high=10),
                    GroupPartition(id=1, offset=7, high=10),
                ],
            )
        ],
    )


RESET_PLAN = OffsetResetPlan("billing", "orders", (OffsetReset(0, 5, 10), OffsetReset(1, None, 10)))


class TestGroupActionsInTopicDetails(unittest.IsolatedAsyncioTestCase):
    async def open_details(
        self, app: KaskadeAdmin, pilot: Any, actions: list[Any] | None
    ) -> DescribeTopicScreen:
        """Open Topic Details, recording group actions unless ``actions`` is ``None``."""
        handler = None if actions is None else lambda _topic, action: actions.append(action)
        app.push_screen(DescribeTopicScreen(topic_with_groups(), (), group_actions=handler))
        await pilot.pause()
        assert isinstance(app.screen, DescribeTopicScreen)
        return app.screen

    async def test_offers_group_actions_only_on_group_tabs(self) -> None:
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                screen = await self.open_details(app, pilot, [])

                self.assertFalse(screen.check_action("reset_offsets", ()))
                self.assertFalse(screen.check_action("delete_group", ()))

                for tab in ("groups", "group-offsets"):
                    with self.subTest(tab=tab):
                        screen.query_one(TabbedContent).active = tab
                        await pilot.pause()
                        help_entries = {entry.description for entry in contextual_help(screen)[1]}

                        self.assertTrue(screen.check_action("reset_offsets", ()))
                        self.assertTrue(screen.check_action("delete_group", ()))
                        self.assertLessEqual({"Reset Offsets", "Delete Group"}, help_entries)

    async def test_hides_and_refuses_group_actions_without_a_handler(self) -> None:
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                screen = await self.open_details(app, pilot, None)
                screen.query_one(TabbedContent).active = "groups"
                await pilot.pause()
                help_entries = {entry.description for entry in contextual_help(screen)[1]}

                self.assertFalse(screen.check_action("reset_offsets", ()))
                self.assertFalse(screen.check_action("delete_group", ()))
                self.assertNotIn("Reset Offsets", help_entries)
                self.assertNotIn("Delete Group", help_entries)

                await pilot.press("r", "ctrl+d")
                await pilot.pause()

                self.assertIs(screen, app.screen)

    async def test_read_only_mode_opens_details_without_group_actions(self) -> None:
        topic = topic_with_groups()
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {topic.name: topic})
            app = KaskadeAdmin({}, settings=replace(load_settings(), admin_read_only=True))
            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                await pilot.pause()

                await pilot.press("d")
                await app.workers.wait_for_complete()
                await pilot.pause()

                self.assertIsInstance(app.screen, DescribeTopicScreen)
                self.assertIsNone(app.screen.group_actions)

    async def test_actions_name_the_selected_group_and_keep_details_open(self) -> None:
        cases = (
            ("groups", "r", GroupAction(GroupActionKind.RESET_OFFSETS, "billing")),
            ("group-offsets", "r", GroupAction(GroupActionKind.RESET_OFFSETS, "billing", 1)),
            ("groups", "ctrl+d", GroupAction(GroupActionKind.DELETE, "billing")),
        )
        for tab, key, expected in cases:
            with (
                self.subTest(tab=tab, key=key),
                patch("kaskade.admin.app.TopicService") as topic_service,
            ):
                configure_admin_service(topic_service.return_value, {})
                app = KaskadeAdmin({})
                actions: list[Any] = []
                async with app.run_test() as pilot:
                    screen = await self.open_details(app, pilot, actions)
                    screen.query_one(TabbedContent).active = tab
                    await pilot.pause()
                    if tab == "group-offsets":
                        screen.query_one("#group-offsets-table", DataTable).move_cursor(row=1)

                    await pilot.press(key)
                    await pilot.pause()

                    self.assertEqual([expected], actions)
                    self.assertIs(screen, app.screen)

    async def test_shows_refreshed_groups_after_a_reset_on_the_same_tab(self) -> None:
        topic = topic_with_groups()
        service = MagicMock()
        configure_admin_service(service, {topic.name: topic})
        service.groups.plan_reset.return_value = RESET_PLAN
        service.groups.apply_reset.return_value = (
            OffsetResetOutcome(0, 10),
            OffsetResetOutcome(1, 10),
        )

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                await pilot.pause()
                await pilot.press("d")
                await app.workers.wait_for_complete()
                await pilot.pause()
                details = app.screen
                assert isinstance(details, DescribeTopicScreen)
                details.query_one(TabbedContent).active = "groups"
                await pilot.pause()

                await pilot.press("r")
                await pilot.pause()
                self.assertIsInstance(app.screen, ResetOffsetsScreen)
                await pilot.press("escape")
                await pilot.pause()
                self.assertIs(details, app.screen)

                refreshed = topic_with_groups()
                refreshed.groups[0].partitions = [
                    GroupPartition(id=0, offset=10, high=10),
                    GroupPartition(id=1, offset=10, high=10),
                ]
                refreshed_groups = refreshed.groups
                configure_admin_service(service, {refreshed.name: refreshed})

                def apply_groups(topics: dict[str, Topic], _snapshot: Any) -> EnrichmentResult:
                    topics[refreshed.name].groups = refreshed_groups
                    return EnrichmentResult()

                service.apply_groups.side_effect = apply_groups
                await pilot.press("r")
                await pilot.pause()
                for _ in range(2):
                    await pilot.press("ctrl+s")
                    await pilot.pause()
                    await app.workers.wait_for_complete()
                    await pilot.pause()
                await pilot.pause(REFRESH_TABLE_DELAY + 0.5)
                await app.workers.wait_for_complete()
                await pilot.pause()

                service.groups.apply_reset.assert_called_once_with(RESET_PLAN)
                self.assertIs(details, app.screen)
                self.assertEqual("groups", details.query_one(TabbedContent).active)
                groups = details.query_one("#groups-table", DataTable)
                self.assertEqual("0", groups.get_row_at(0)[-1])


class TestResetOffsets(unittest.IsolatedAsyncioTestCase):
    async def open_reset_form(
        self, app: KaskadeAdmin, pilot: Any, *, partition: int | None = None
    ) -> ListTopics:
        await app.workers.wait_for_complete()
        topics = app.query_one(ListTopics)
        topics._start_group_action(
            topic_with_groups(),
            GroupAction(GroupActionKind.RESET_OFFSETS, "billing", partition),
        )
        await pilot.pause()
        self.assertIsInstance(app.screen, ResetOffsetsScreen)
        return topics

    async def press_and_settle(self, app: KaskadeAdmin, pilot: Any, key: str) -> None:
        await pilot.press(key)
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

    def select_target(self, app: KaskadeAdmin, target: OffsetTarget) -> None:
        buttons = app.screen.query("#reset-target RadioButton").results(RadioButton)
        next(button for button in buttons if str(button.label) == target.value).value = True

    async def test_reviews_then_applies_the_planned_offsets(self) -> None:
        service = MagicMock()
        configure_admin_service(service, {})
        service.groups.plan_reset.return_value = RESET_PLAN
        service.groups.apply_reset.return_value = (
            OffsetResetOutcome(0, 10),
            OffsetResetOutcome(1, 10),
        )

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await self.open_reset_form(app, pilot)
                app.notify = MagicMock()
                self.select_target(app, OffsetTarget.LATEST)

                await self.press_and_settle(app, pilot, "ctrl+s")

                service.groups.plan_reset.assert_called_once_with(
                    ResetOffsetsCommand("billing", "orders", (0, 1), OffsetTarget.LATEST)
                )
                self.assertIsInstance(app.screen, ReviewOffsetResetScreen)
                table = app.screen.query_one("#offset-resets", DataTable)
                self.assertEqual(
                    [["0", "5", "10"], ["1", "—", "10"]],
                    [table.get_row_at(index) for index in range(table.row_count)],
                )

                await self.press_and_settle(app, pilot, "ctrl+s")

                service.groups.apply_reset.assert_called_once_with(RESET_PLAN)
                self.assertIs(app.screen, app.screen_stack[0])
                app.notify.assert_any_call(
                    "Reset 2 of 2 partitions of group 'billing'\nPartition 0: 10\nPartition 1: 10",
                    title="Offsets Reset",
                    severity="information",
                )

    async def test_back_from_review_returns_to_the_form_without_applying(self) -> None:
        service = MagicMock()
        configure_admin_service(service, {})
        service.groups.plan_reset.return_value = RESET_PLAN

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await self.open_reset_form(app, pilot, partition=1)
                self.assertEqual("1", app.screen.query_one("#reset-partitions", Input).value)

                await self.press_and_settle(app, pilot, "ctrl+s")
                await self.press_and_settle(app, pilot, "escape")

                self.assertIsInstance(app.screen, ResetOffsetsScreen)
                await self.press_and_settle(app, pilot, "escape")

                self.assertIs(app.screen, app.screen_stack[0])
                service.groups.apply_reset.assert_not_called()

    async def test_refuses_a_group_with_active_members(self) -> None:
        service = MagicMock()
        configure_admin_service(service, {})
        service.groups.plan_reset.side_effect = GroupNotEmptyError("billing", 2)

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await self.open_reset_form(app, pilot)
                app.notify = MagicMock()

                await self.press_and_settle(app, pilot, "ctrl+s")

                self.assertIsInstance(app.screen, ResetOffsetsScreen)
                app.notify.assert_called_once_with(
                    "Group 'billing' has 2 active members; stop its consumers first",
                    title="Group Not Empty",
                    severity="warning",
                )

    async def test_reports_kafka_errors_while_planning(self) -> None:
        service = MagicMock()
        configure_admin_service(service, {})
        service.groups.plan_reset.side_effect = KafkaException(
            KafkaError(KafkaError.GROUP_AUTHORIZATION_FAILED)
        )

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await self.open_reset_form(app, pilot)
                app.notify = MagicMock()

                await self.press_and_settle(app, pilot, "ctrl+s")

                self.assertIsInstance(app.screen, ResetOffsetsScreen)
                self.assertEqual("Kafka Error", app.notify.call_args.kwargs["title"])

    async def test_rejects_invalid_values_before_planning(self) -> None:
        cases = (
            (OffsetTarget.TIMESTAMP, "yesterday", "", "Timestamp:"),
            (OffsetTarget.OFFSET, "-1", "", "Offset:"),
            (OffsetTarget.EARLIEST, "", "0,0", "Partitions:"),
            (OffsetTarget.EARLIEST, "", "2", "Partitions:"),
        )
        for target, value, partitions, failure in cases:
            service = MagicMock()
            configure_admin_service(service, {})
            with (
                self.subTest(target=target, value=value, partitions=partitions),
                patch("kaskade.admin.app.TopicService", return_value=service),
            ):
                app = KaskadeAdmin({})
                async with app.run_test() as pilot:
                    await self.open_reset_form(app, pilot)
                    app.notify = MagicMock()
                    self.select_target(app, target)
                    await pilot.pause()
                    app.screen.query_one("#reset-value", Input).value = value
                    app.screen.query_one("#reset-partitions", Input).value = partitions

                    await self.press_and_settle(app, pilot, "ctrl+s")

                    service.groups.plan_reset.assert_not_called()
                    self.assertTrue(app.notify.call_args.args[0].startswith(failure))

    async def test_value_input_follows_the_target(self) -> None:
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await self.open_reset_form(app, pilot)
                value = app.screen.query_one("#reset-value", Input)
                self.assertTrue(value.disabled)

                self.select_target(app, OffsetTarget.TIMESTAMP)
                await pilot.pause()

                self.assertFalse(value.disabled)
                self.assertEqual("Timestamp", value.border_title)

    async def test_reports_each_failed_partition(self) -> None:
        service = MagicMock()
        configure_admin_service(service, {})
        service.groups.apply_reset.return_value = (
            OffsetResetOutcome(0, 10),
            OffsetResetOutcome(1, 10, "Broker: Topic authorization failed"),
        )

        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            app.notify = MagicMock()
            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                worker = app.query_one(ListTopics).reset_offsets(RESET_PLAN)
                await worker.wait()
                await pilot.pause()

                app.notify.assert_any_call(
                    "Reset 1 of 2 partitions of group 'billing'\n"
                    "Partition 1: Broker: Topic authorization failed",
                    title="Offsets Partially Reset",
                    severity="warning",
                )


class TestDeleteGroup(unittest.IsolatedAsyncioTestCase):
    async def delete(self, service: MagicMock, confirmation: str = "billing") -> KaskadeAdmin:
        with patch("kaskade.admin.app.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                app.notify = MagicMock()
                app.query_one(ListTopics)._start_group_action(
                    topic_with_groups(), GroupAction(GroupActionKind.DELETE, "billing")
                )
                await pilot.pause()
                self.assertIsInstance(app.screen, DeleteGroupScreen)
                app.screen.query_one("#group-confirmation", Input).value = confirmation

                await pilot.press("enter")
                await pilot.pause()
                await app.workers.wait_for_complete()
                await pilot.pause()
        return app

    async def test_deletes_a_confirmed_group(self) -> None:
        service = MagicMock()
        configure_admin_service(service, {})

        app = await self.delete(service)

        service.groups.delete.assert_called_once_with("billing")
        app.notify.assert_any_call(
            "Deleted group 'billing'", title="Group Deleted", severity="information"
        )

    async def test_requires_the_exact_group_id(self) -> None:
        service = MagicMock()
        configure_admin_service(service, {})

        await self.delete(service, confirmation="bill")

        service.groups.delete.assert_not_called()

    async def test_refuses_a_group_with_active_members(self) -> None:
        service = MagicMock()
        configure_admin_service(service, {})
        service.groups.delete.side_effect = GroupNotEmptyError("billing", 1)

        app = await self.delete(service)

        app.notify.assert_any_call(
            "Group 'billing' has 1 active member; stop its consumers first",
            title="Group Not Empty",
            severity="warning",
        )


class TestResetInputParsing(unittest.TestCase):
    def test_parses_partitions(self) -> None:
        self.assertEqual((0, 1, 2), parse_partitions("", 3))
        self.assertEqual((2, 0), parse_partitions(" 2, 0 ", 3))
        for invalid in ("3", "0,0", "a", "1,", "-1"):
            with self.subTest(value=invalid):
                self.assertIsNone(parse_partitions(invalid, 3))

    def test_describes_the_partition_ids_in_the_placeholder(self) -> None:
        self.assertEqual("Empty for all, or 0", partitions_placeholder(1))
        self.assertEqual(
            "Empty for all, or comma-separated IDs from 0 to 9", partitions_placeholder(10)
        )

    def test_parses_timestamps(self) -> None:
        self.assertEqual(1_700_000_000_000, parse_timestamp("1700000000000"))
        self.assertEqual(1_700_000_000_000, parse_timestamp("2023-11-14T22:13:20+00:00"))
        self.assertIsNone(parse_timestamp("yesterday"))
