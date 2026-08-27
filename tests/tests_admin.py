import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from confluent_kafka import KafkaException
from confluent_kafka.cimpl import NewTopic
from textual.widgets import DataTable, Input

from kaskade.admin import CreateTopicScreen, FilterTopicsScreen, KaskadeAdmin, ListTopics
from kaskade.keymaps import CONFIG_ENV_VAR
from kaskade.models import MetricState, Partition, Topic
from kaskade.services import EnrichmentResult, GroupSnapshot
from tests import configure_admin_service


class TestCreateTopic(unittest.IsolatedAsyncioTestCase):
    async def test_keeps_invalid_topic_configuration_open(self) -> None:
        with patch("kaskade.admin.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})
            results: list[NewTopic | None] = []

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
                self.assertEqual("orders", results[0].topic)

    async def test_stops_loading_when_kafka_rejects_topic(self) -> None:
        with patch("kaskade.admin.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            topic_service.return_value.create.side_effect = KafkaException("invalid topic")
            app = KaskadeAdmin({})

            async with app.run_test() as pilot:
                await pilot.pause()
                topics = app.query_one(ListTopics)
                table = app.query_one("#topics-table", DataTable)

                worker = topics.create_topic(NewTopic("orders", 1, 1))
                await worker.wait()
                await pilot.pause()

                self.assertFalse(table.loading)


class TestAdminRefresh(unittest.IsolatedAsyncioTestCase):
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
