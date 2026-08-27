import unittest
from unittest.mock import AsyncMock, patch

from confluent_kafka import KafkaException
from confluent_kafka.cimpl import NewTopic
from textual.widgets import DataTable, Input

from kaskade.admin import CreateTopicScreen, KaskadeAdmin, ListTopics


class TestCreateTopic(unittest.IsolatedAsyncioTestCase):
    async def test_keeps_invalid_topic_configuration_open(self) -> None:
        with patch("kaskade.admin.TopicService") as topic_service:
            topic_service.return_value.all = AsyncMock(return_value={})
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
            topic_service.return_value.all = AsyncMock(return_value={})
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
