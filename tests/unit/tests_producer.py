import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from textual.widgets import Checkbox, DataTable, Input, Select, Static, TabbedContent, TextArea

from kaskade.configs import BOOTSTRAP_SERVERS
from kaskade.producer import HeaderScreen, KaskadeProducer, RecordComposer, RecordDraft
from kaskade.producer.source import DraftField
from kaskade.producer_service import (
    Delivery,
    DeliveryError,
    DeliveryFailure,
    OutgoingRecord,
    ProducerSettings,
)
from kaskade.serializers import Serialization
from tests import configure_producer_service

DELIVERY = Delivery(2, 8429, datetime(2026, 10, 8, 14, 20, 5, 120000, tzinfo=timezone.utc))


def producer_app(
    *,
    drafts: tuple[RecordDraft, ...] = (),
    value_serialization: Serialization = Serialization.STRING,
    partition: int | None = None,
) -> KaskadeProducer:
    settings = ProducerSettings(
        "orders",
        {BOOTSTRAP_SERVERS: "kafka:9092"},
        value_serialization=value_serialization,
        partition=partition,
    )
    return KaskadeProducer(settings, drafts=drafts)


class ProducerTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        patcher = patch("kaskade.producer.app.ProducerService")
        self.addCleanup(patcher.stop)
        self.service = patcher.start().return_value
        configure_producer_service(self.service)
        self.service.produce.return_value = DELIVERY

    @staticmethod
    def composer(app: KaskadeProducer) -> RecordComposer:
        return app.query_one(RecordComposer)

    @staticmethod
    def produced(service: MagicMock) -> OutgoingRecord:
        return service.produce.call_args.args[0]


class TestHeaders(ProducerTestCase):
    async def add_header(self, pilot, app, name: str, value: str | None) -> None:
        await pilot.press("n")
        await pilot.pause()
        screen = app.screen
        self.assertIsInstance(screen, HeaderScreen)
        screen.query_one("#header-name", Input).value = name
        screen.query_one("#header-value", Input).value = value or ""
        screen.query_one("#header-null", Checkbox).value = value is None
        await pilot.press("ctrl+s")
        await pilot.pause()

    async def test_headers_keep_order_duplicates_empty_and_null_values(self):
        app = producer_app()
        async with app.run_test() as pilot:
            app.query_one("#headers-table", DataTable).focus()
            await self.add_header(pilot, app, "trace", "a")
            await self.add_header(pilot, app, "trace", None)
            await self.add_header(pilot, app, "empty", "")
            await pilot.press("ctrl+s")
            await pilot.pause()

            self.assertEqual(
                (("trace", "a"), ("trace", None), ("empty", "")),
                self.produced(self.service).headers,
            )
            tab = app.query_one(TabbedContent).get_tab("headers-tab")
            self.assertEqual("Headers [3]", str(tab.label))

    async def test_edit_and_delete_the_selected_header(self):
        app = producer_app(drafts=(RecordDraft(headers=(("a", "1"), ("b", "2"))),))
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#headers-table", DataTable)
            table.focus()
            await pilot.press("e")
            await pilot.pause()
            app.screen.query_one("#header-value", Input).value = "changed"
            await pilot.press("ctrl+s")
            await pilot.pause()
            await pilot.press("down", "ctrl+d")
            await pilot.pause()

            self.assertEqual(
                [("a", "changed")], self.composer(app).query_one("#headers-pane").headers
            )

    async def test_empty_header_name_is_rejected(self):
        app = producer_app()
        async with app.run_test() as pilot:
            app.query_one("#headers-table", DataTable).focus()
            await pilot.press("n")
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()

            self.assertIsInstance(app.screen, HeaderScreen)


class TestComposeAndProduce(ProducerTestCase):
    async def test_empty_content_is_distinct_from_null(self):
        app = producer_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#value-null", Checkbox).value = True
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()

            record = self.produced(self.service)
            self.assertEqual(b"", record.key)
            self.assertIsNone(record.value)
            self.assertTrue(app.query_one("#value-content", TextArea).disabled)

    async def test_invalid_content_keeps_focus_and_produces_nothing(self):
        app = producer_app(value_serialization=Serialization.INTEGER)
        async with app.run_test() as pilot:
            app.query_one("#value-content", TextArea).load_text("twelve")
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()

            self.service.produce.assert_not_called()
            self.assertEqual("value-tab", app.query_one(TabbedContent).active)
            self.assertIs(app.focused, app.query_one("#value-content", TextArea))
            status = app.query_one("#value-status", Static).render()
            self.assertIn("Expected a 32-bit integer", str(status))
            self.assertIn("Value: Expected", str(app.query_one("#record-preview", Static).render()))

    async def test_success_reports_the_acknowledgement_and_keeps_the_draft(self):
        app = producer_app(partition=2)
        async with app.run_test() as pilot:
            app.query_one("#key-content", TextArea).load_text("order-1")
            app.query_one("#value-serializer", Select).value = "json"
            app.query_one("#value-content", TextArea).load_text('{"status": "paid"}')
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()

            record = self.produced(self.service)
            self.assertEqual(b"order-1", record.key)
            self.assertEqual(b'{"status":"paid"}', record.value)
            self.assertEqual(2, record.partition)
            composer = self.composer(app)
            self.assertIn("Delivered · Partition 2 · Offset 8429", composer.border_subtitle)
            self.assertEqual("order-1", app.query_one("#key-content", TextArea).text)
            self.assertTrue(composer.check_action("produce", ()))

    async def test_failure_keeps_the_draft_and_enables_produce(self):
        self.service.produce.side_effect = DeliveryError(
            DeliveryFailure.AUTHORIZATION, "Topic authorization failed"
        )
        app = producer_app()
        async with app.run_test() as pilot:
            app.query_one("#value-content", TextArea).load_text("payload")
            await pilot.pause()
            with self.assertLogs("kaskade", level="ERROR") as logs:
                await pilot.press("ctrl+s")
                await pilot.pause()

            composer = self.composer(app)
            self.assertIn("Authorization Error", composer.border_subtitle)
            self.assertEqual("payload", app.query_one("#value-content", TextArea).text)
            self.assertTrue(composer.check_action("produce", ()))
            self.assertNotIn("payload", "\n".join(logs.output))

    async def test_produce_is_disabled_while_a_delivery_is_in_progress(self):
        release = asyncio.Event()

        async def produce(_: OutgoingRecord) -> Delivery:
            await release.wait()
            return DELIVERY

        self.service.produce = AsyncMock(side_effect=produce)
        app = producer_app()
        async with app.run_test() as pilot:
            await pilot.press("ctrl+s")
            await pilot.pause()
            composer = self.composer(app)
            self.assertIsNone(composer.check_action("produce", ()))
            self.assertIn("Producing", composer.border_subtitle)

            await pilot.press("ctrl+s")
            await pilot.pause()
            release.set()
            await pilot.pause()

            self.assertEqual(1, self.service.produce.call_count)
            self.assertTrue(composer.check_action("produce", ()))

    async def test_source_drafts_load_and_navigate(self):
        drafts = (
            RecordDraft(key=DraftField("first", is_null=False)),
            RecordDraft(value=DraftField({"n": 2}, is_null=False)),
        )
        app = producer_app(drafts=drafts, value_serialization=Serialization.JSON)
        async with app.run_test() as pilot:
            await pilot.pause()
            composer = self.composer(app)
            self.assertIn("Record 1/2", composer.border_title)
            self.assertEqual("first", app.query_one("#key-content", TextArea).text)

            await pilot.press("ctrl+pagedown")
            await pilot.pause()

            self.assertIn("Record 2/2", composer.border_title)
            self.assertTrue(app.query_one("#key-null", Checkbox).value)
            self.assertEqual('{\n  "n": 2\n}', app.query_one("#value-content", TextArea).text)
            self.service.produce.assert_not_called()

    async def test_draft_navigation_is_hidden_without_several_drafts(self):
        app = producer_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertFalse(self.composer(app).check_action("next_draft", ()))

    async def test_shutdown_closes_the_producer(self):
        app = producer_app()
        async with app.run_test() as pilot:
            await pilot.pause()

        self.service.aclose.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
