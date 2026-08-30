import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from confluent_kafka import KafkaException
from textual.widgets import DataTable, Input

from kaskade.admin import (
    CreateTopicScreen,
    DescribeTopicScreen,
    EditTopicScreen,
    FilterTopicsScreen,
    KaskadeAdmin,
    ListTopics,
    RefreshCoordinator,
    RefreshReason,
)
from kaskade.commands import CreateTopicCommand, UpdateTopicCommand
from kaskade.keymaps import CONFIG_ENV_VAR
from kaskade.models import MetricState, Partition, Topic
from kaskade.services import EnrichmentResult, GroupSnapshot
from tests import configure_admin_service


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


class TestCreateTopic(unittest.IsolatedAsyncioTestCase):
    async def test_keeps_invalid_topic_configuration_open(self) -> None:
        with patch("kaskade.admin.TopicService") as topic_service:
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
        with patch("kaskade.admin.TopicService") as topic_service:
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
    async def test_rejects_partition_decreases_before_mutating(self) -> None:
        app = KaskadeAdmin({})
        results: list[UpdateTopicCommand | None] = []

        with patch("kaskade.admin.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            async with app.run_test() as pilot:
                app.push_screen(
                    EditTopicScreen("orders", "3", "1", "delete", "1000"), results.append
                )
                await pilot.pause()
                app.screen.query_one("#partitions", Input).value = "2"

                await pilot.press("ctrl+s")

                self.assertIsInstance(app.screen, EditTopicScreen)
                self.assertEqual([], results)

    async def test_refreshes_after_partial_topic_update(self) -> None:
        topic = Topic(name="orders", partitions=[Partition(id=0, topic="orders")])
        service = MagicMock()
        configure_admin_service(service, {topic.name: topic})
        service.edit.side_effect = KafkaException("config rejected")

        with patch("kaskade.admin.TopicService", return_value=service):
            app = KaskadeAdmin({})
            app.notify = MagicMock()
            async with app.run_test() as pilot:
                await app.workers.wait_for_complete()
                topics = app.query_one(ListTopics)
                with patch.object(topics, "set_timer") as set_timer:
                    worker = topics.update_topic(
                        topic,
                        UpdateTopicCommand(2, 1, "delete", 1000),
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


class TestTopicCopyActions(unittest.IsolatedAsyncioTestCase):
    async def test_y_copies_topic_from_table_and_details(self) -> None:
        topic = Topic(name="orders")
        with patch("kaskade.admin.TopicService") as topic_service:
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

                app.push_screen(DescribeTopicScreen(topic))
                await pilot.pause()
                app.copy_to_clipboard("")
                app.notify.reset_mock()

                await pilot.press("y")

                self.assertEqual("orders", app.clipboard)
                app.notify.assert_called_once_with(
                    "Copied topic name to clipboard",
                    title="Copied",
                )

    async def test_copy_is_disabled_without_a_topic(self) -> None:
        with patch("kaskade.admin.TopicService") as topic_service:
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

        with patch("kaskade.admin.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await pilot.pause()
                self.assertEqual(1, len(app.query_one(DataTable).rows))

    async def test_command_line_interval_overrides_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.yaml"
            config_path.write_text(
                "admin:\n  refresh_interval_seconds: 60\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {CONFIG_ENV_VAR: str(config_path)}):
                app = KaskadeAdmin({}, refresh_interval=10)

                self.assertEqual(10, app.auto_refresh_interval)

    async def test_can_disable_auto_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.yaml"
            config_path.write_text(
                "admin:\n  refresh_interval_seconds: 0\n",
                encoding="utf-8",
            )
            with (
                patch.dict(os.environ, {CONFIG_ENV_VAR: str(config_path)}),
                patch("kaskade.admin.TopicService") as topic_service,
            ):
                configure_admin_service(topic_service.return_value, {})
                app = KaskadeAdmin({})
                async with app.run_test() as pilot:
                    await app.workers.wait_for_complete()
                    await pilot.pause()

                    self.assertEqual(0, app.auto_refresh_interval)
                    self.assertIsNone(app._auto_refresh_timer)
                    self.assertIn("Auto Off", app.query_one(DataTable).border_subtitle)

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

        with patch("kaskade.admin.TopicService", return_value=service):
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

        with patch("kaskade.admin.TopicService", return_value=service):
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

        with patch("kaskade.admin.TopicService", return_value=service):
            app = KaskadeAdmin({})
            async with app.run_test() as pilot:
                await pilot.pause()
                topics = app.query_one(ListTopics)
                topics.request_refresh(RefreshReason.MANUAL)
                topics.request_refresh(RefreshReason.MANUAL)

                self.assertEqual(1, service.metadata.call_count)
                first_refresh_gate.set()
                await app.workers.wait_for_complete()
                await pilot.pause()
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

        with patch("kaskade.admin.TopicService", return_value=service):
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

        with patch("kaskade.admin.TopicService", return_value=service):
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

        with patch("kaskade.admin.TopicService", return_value=service):
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
