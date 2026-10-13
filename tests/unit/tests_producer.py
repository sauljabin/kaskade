import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from textual.widgets import Checkbox, Input, Select, Static, TabbedContent, TextArea

from kaskade.configs import BOOTSTRAP_SERVERS
from kaskade.producer import KaskadeProducer, RecordComposer, RecordDraft
from kaskade.producer.composer import HeaderRow
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
    @staticmethod
    def rows(app: KaskadeProducer) -> list[HeaderRow]:
        return list(app.query(HeaderRow))

    async def fill(self, pilot, app, name: str, value: str | None) -> None:
        """Type into the trailing blank row, as a user would."""
        row = self.rows(app)[-1]
        row.query_one(".header-name", Input).value = name
        await pilot.pause()
        row.query_one(".header-value", Input).value = value or ""
        row.query_one(".header-null", Checkbox).value = value is None
        await pilot.pause()

    async def test_typing_in_the_last_row_adds_another(self):
        app = producer_app()
        async with app.run_test() as pilot:
            app.query_one(TabbedContent).active = "headers-tab"
            await pilot.pause()
            self.assertEqual(1, len(self.rows(app)))

            await self.fill(pilot, app, "trace", "a")
            await self.fill(pilot, app, "trace", None)
            await self.fill(pilot, app, "empty", "")
            await pilot.press("ctrl+s")
            await pilot.pause()

            self.assertEqual(4, len(self.rows(app)))
            self.assertTrue(self.rows(app)[-1].is_blank)
            self.assertEqual(
                (("trace", "a"), ("trace", None), ("empty", "")),
                self.produced(self.service).headers,
            )
            tab = app.query_one(TabbedContent).get_tab("headers-tab")
            self.assertEqual("Headers [3]", str(tab.label))
            self.assertTrue(self.rows(app)[1].query_one(".header-value", Input).disabled)

    async def test_delete_removes_the_focused_header(self):
        app = producer_app(drafts=(RecordDraft(headers=(("a", "1"), ("b", "2"))),))
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one(TabbedContent).active = "headers-tab"
            await pilot.pause()
            self.rows(app)[0].name_input.focus()
            await pilot.press("ctrl+d")
            await pilot.pause()

            self.assertEqual([("b", "2")], app.query_one("#headers-pane").headers)
            self.assertIs(app.focused, self.rows(app)[0].name_input)

    async def test_many_headers_scroll_and_keep_columns_aligned(self):
        headers = tuple((f"header-{index}", f"value-{index}") for index in range(12))
        app = producer_app(drafts=(RecordDraft(headers=headers),))
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            app.query_one(TabbedContent).active = "headers-tab"
            await pilot.pause()
            container = app.query_one("#header-rows")
            label = app.query_one(".header-labels > .column-null")

            self.assertGreater(container.max_scroll_y, 0)
            self.assertTrue(container.show_vertical_scrollbar)
            self.assertEqual(label.region.x, self.rows(app)[0].query_one(".column-null").region.x)

            self.rows(app)[-1].name_input.focus()
            await pilot.wait_for_scheduled_animations()
            self.assertEqual(container.max_scroll_y, container.scroll_y)

    async def test_a_header_without_a_name_blocks_production(self):
        app = producer_app()
        async with app.run_test() as pilot:
            app.query_one(TabbedContent).active = "headers-tab"
            await pilot.pause()
            await self.fill(pilot, app, "", "orphan")
            await pilot.press("ctrl+s")
            await pilot.pause()

            self.service.produce.assert_not_called()
            self.assertIs(app.focused, self.rows(app)[0].name_input)
            subtitle = str(self.composer(app).frame.border_subtitle)
            self.assertIn("Header 1 needs a name", subtitle)
            unnamed = self.rows(app)[0]
            self.assertTrue(unnamed.has_class("-invalid"))
            self.assertEqual("Name required", unnamed.name_input.placeholder)

            unnamed.name_input.value = "trace"
            await pilot.pause()
            self.assertFalse(unnamed.has_class("-invalid"))


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
            subtitle = str(self.composer(app).frame.border_subtitle)
            self.assertIn("Value Expected a 32-bit integer", subtitle)
            editor = app.query_one("#value-editor")
            self.assertTrue(editor.has_class("-invalid"))
            summary = app.query_one("#summary-status", Static)
            self.assertIn("Invalid Value", str(summary.render()))
            self.assertTrue(summary.has_class("-invalid"))

            app.query_one("#value-content", TextArea).load_text("12")
            await pilot.pause()
            self.assertFalse(editor.has_class("-invalid"))

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
            self.assertIn("Delivered · Partition 2 · Offset 8429", composer.frame.border_subtitle)
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
            self.assertIn("Authorization Error", composer.frame.border_subtitle)
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
            self.assertIn("Producing", composer.frame.border_subtitle)

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
            self.assertIn("Record 1/2", composer.frame.border_title)
            self.assertEqual("first", app.query_one("#key-content", TextArea).text)

            await pilot.press("ctrl+pagedown")
            await pilot.pause()

            self.assertIn("Record 2/2", composer.frame.border_title)
            self.assertTrue(app.query_one("#key-null", Checkbox).value)
            self.assertEqual('{\n  "n": 2\n}', app.query_one("#value-content", TextArea).text)
            self.service.produce.assert_not_called()

    async def test_draft_navigation_is_hidden_without_several_drafts(self):
        app = producer_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertFalse(self.composer(app).check_action("next_draft", ()))

    async def test_summary_sits_beside_the_frame_and_toggles(self):
        app = producer_app(partition=2)
        async with app.run_test(size=(120, 30)) as pilot:
            app.query_one("#key-content", TextArea).load_text("order-1")
            app.query_one("#value-null", Checkbox).value = True
            await pilot.pause()
            summary = app.query_one("#record-summary")
            frame = self.composer(app).frame

            self.assertTrue(summary.display)
            self.assertLessEqual(frame.region.right, summary.region.x)

            def cell(name: str) -> str:
                return str(app.query_one(f"#summary-{name}", Static).render())

            self.assertIn("2", cell("partition"))
            self.assertIn("STRING", cell("key-serializer"))
            self.assertIn("7 bytes", cell("key-size"))
            self.assertIn("Null", cell("value-size"))
            self.assertIn("Ready to produce", cell("status"))

            await pilot.press("f3")
            await pilot.pause()
            self.assertFalse(summary.display)
            self.assertEqual(120 - 2, frame.region.width)

    async def test_summary_starts_hidden_on_narrow_terminals(self):
        app = producer_app()
        async with app.run_test(size=(70, 24)) as pilot:
            await pilot.pause()
            self.assertFalse(app.query_one("#record-summary").display)

    async def test_produce_has_zellij_safe_aliases(self):
        app = producer_app()
        async with app.run_test() as pilot:
            await pilot.press("f2")
            await pilot.pause()

            self.service.produce.assert_called_once()

    async def test_shutdown_closes_the_producer(self):
        app = producer_app()
        async with app.run_test() as pilot:
            await pilot.pause()

        self.service.aclose.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
