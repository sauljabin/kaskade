import asyncio
import json
import struct
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from confluent_kafka.schema_registry.error import SchemaRegistryError
from rich.console import Console
from rich.style import Style
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

AVRO_USER_SCHEMA = {
    "type": "record",
    "name": "User",
    "fields": [{"name": "name", "type": "string"}],
}
DELIVERY = Delivery(2, 8429, datetime(2026, 10, 8, 14, 20, 5, 120000, tzinfo=timezone.utc))


def producer_app(
    *,
    draft: RecordDraft | None = None,
    value_serialization: Serialization = Serialization.STRING,
    partition: int | None = None,
    **options: Any,
) -> KaskadeProducer:
    settings = ProducerSettings(
        "orders",
        {BOOTSTRAP_SERVERS: "kafka:9092"},
        value_serialization=value_serialization,
        partition=partition,
        **options,
    )
    return KaskadeProducer(settings, draft=draft)


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
    def status_text(app: KaskadeProducer) -> str:
        """The Summary status as plain text, however it is laid out."""
        console = Console(width=80, color_system=None)
        with console.capture() as capture:
            console.print(app.query_one("#summary-status", Static).content)
        return capture.get()

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

            def cell(name: str) -> str:
                return str(app.query_one(f"#summary-headers-{name}", Static).render())

            self.assertIn("3", cell("count"))
            self.assertIn("16 bytes", cell("size"))
            total = str(app.query_one("#summary-total-size", Static).render())
            self.assertIn("16 bytes", total)
            subtitle = self.composer(app).frame.border_subtitle
            self.assertIn("Headers: 16 bytes", subtitle)

    async def test_delete_removes_the_focused_header(self):
        app = producer_app(draft=RecordDraft(headers=(("a", "1"), ("b", "2"))))
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
        app = producer_app(draft=RecordDraft(headers=headers))
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
            self.assertIn("Header 1: Needs a name", subtitle)
            self.assertIn("Header 1", self.status_text(app))
            self.assertIn("Needs a name", self.status_text(app))
            unnamed = self.rows(app)[0]
            self.assertTrue(unnamed.has_class("-invalid"))
            self.assertEqual("Name required", unnamed.name_input.placeholder)

            unnamed.name_input.value = "trace"
            await pilot.pause()
            self.assertFalse(unnamed.has_class("-invalid"))


class TestComposeAndProduce(ProducerTestCase):
    async def test_serializers_come_only_from_the_command_line(self):
        app = producer_app(
            value_serialization=Serialization.BYTES, bytes_config={"value.encoding": "hex"}
        )
        async with app.run_test() as pilot:
            app.query_one("#value-content", TextArea).load_text("00ff")
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()

            self.assertEqual([], list(app.query(Select)))
            options = app.query_one("#value-editor .field-options")
            self.assertEqual(["value-null"], [child.id for child in options.children])
            self.assertEqual(b"\x00\xff", self.produced(self.service).value)
            serializer = str(app.query_one("#summary-value-serializer", Static).render())
            self.assertIn("BYTES · HEX", serializer)

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
            self.assertIn("Value: Expected a 32-bit integer", subtitle)
            editor = app.query_one("#value-editor")
            self.assertTrue(editor.has_class("-invalid"))
            summary = app.query_one("#summary-status", Static)
            self.assertIn("Expected a 32-bit integer", self.status_text(app))
            total = str(app.query_one("#summary-total-size", Static).render())
            self.assertIn("Invalid", total)
            self.assertTrue(summary.has_class("-invalid"))

            app.query_one("#value-content", TextArea).load_text("12")
            await pilot.pause()
            self.assertFalse(editor.has_class("-invalid"))

    async def test_success_reports_the_acknowledgement_and_keeps_the_draft(self):
        app = producer_app(partition=2, value_serialization=Serialization.JSON)
        async with app.run_test() as pilot:
            app.query_one("#key-content", TextArea).load_text("order-1")
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
            self.assertIn("Key: 7 bytes", composer.frame.border_subtitle)
            self.assertNotIn("Valid", composer.frame.border_subtitle)
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

    async def test_source_draft_loads_without_producing(self):
        draft = RecordDraft(
            key=DraftField("first", is_null=False), value=DraftField({"n": 2}, is_null=False)
        )
        app = producer_app(draft=draft, value_serialization=Serialization.JSON)
        async with app.run_test() as pilot:
            await pilot.pause()

            self.assertEqual("first", app.query_one("#key-content", TextArea).text)
            self.assertEqual('{\n  "n": 2\n}', app.query_one("#value-content", TextArea).text)
            self.service.produce.assert_not_called()

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
            self.assertIn("7 bytes", cell("total-size"))
            self.assertIn("all", cell("acks"))
            self.assertIn("false", cell("enable-idempotence"))
            self.assertIn("none", cell("compression-type"))
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


class TestJsonHighlighting(ProducerTestCase):
    async def test_highlights_only_serializers_whose_input_is_json(self):
        app = producer_app(value_serialization=Serialization.JSON)
        async with app.run_test() as pilot:
            await pilot.pause()

            self.assertIsNone(app.query_one("#key-content", TextArea).language)
            self.assertEqual("json", app.query_one("#value-content", TextArea).language)

        app = producer_app(
            value_serialization=Serialization.BYTES, bytes_config={"encoding": "byte-array"}
        )
        async with app.run_test() as pilot:
            await pilot.pause()

            self.assertEqual("json", app.query_one("#value-content", TextArea).language)

    async def test_colors_follow_the_theme(self):
        app = producer_app(value_serialization=Serialization.JSON)
        async with app.run_test() as pilot:
            await pilot.pause()
            value = app.query_one("#value-content", TextArea)

            app.query_one(TabbedContent).active = "value-tab"
            value.load_text('{"id": 1}')
            for theme in ("eva01-berserk", "textual-light", "ansi-dark"):
                app.theme = theme
                await pilot.pause()
                with self.subTest(theme=theme):
                    self.assertEqual(f"kaskade-json-{theme}", value.theme)
                    expected = Style.parse(app.semantic_styles()["json.key"])
                    key_style = self.drawn_style(value, '"id"')
                    self.assertEqual(expected.color, key_style.color)
                    self.assertTrue(key_style.bold)

    @staticmethod
    def drawn_style(editor: TextArea, text: str) -> Style:
        """The style the editor draws a piece of text with."""
        for y in range(editor.size.height):
            for segment in editor.render_line(y):
                if segment.text == text:
                    return segment.style
        raise AssertionError(f"{text!r} is not drawn")


class TestRegistryLookup(ProducerTestCase):
    def setUp(self) -> None:
        super().setUp()
        patcher = patch("kaskade.serializers.registry.SchemaRegistryClient")
        self.addCleanup(patcher.stop)
        self.client = patcher.start().return_value
        self.client.get_schema.return_value = SimpleNamespace(
            schema_str=json.dumps(AVRO_USER_SCHEMA), schema_type="AVRO", references=[]
        )

    @staticmethod
    def registry_app() -> KaskadeProducer:
        return producer_app(
            value_serialization=Serialization.REGISTRY,
            registry_config={"url": "http://registry"},
        )

    @staticmethod
    def cell(app: KaskadeProducer, name: str) -> str:
        return str(app.query_one(f"#summary-value-{name}", Static).render())

    async def test_looks_up_the_schema_and_shows_it_in_the_summary(self):
        self.client.get_latest_version.return_value = SimpleNamespace(schema_id=7, version=3)
        app = self.registry_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            app.query_one("#value-content", TextArea).load_text('{"name": "Ada"}')
            await pilot.pause()

            self.assertIn("REGISTRY · AVRO", self.cell(app, "serializer"))
            self.assertIn("orders-value", self.cell(app, "schema-schema"))
            self.assertIn("3", self.cell(app, "schema-version"))
            self.assertIn("7", self.cell(app, "schema-id"))
            self.assertIn("SCHEMA ID", self.cell(app, "schema-id"))
            self.assertEqual("json", app.query_one("#value-content", TextArea).language)
            await pilot.press("ctrl+s")
            await pilot.pause()

            self.assertEqual(
                struct.pack(">bI", 0, 7) + b"\x06Ada", self.produced(self.service).value
            )
        self.client.get_latest_version.assert_called_once_with("orders-value")
        self.client.close.assert_called_once_with()

    async def test_a_failed_lookup_blocks_production_and_retries_on_produce(self):
        self.client.get_latest_version.side_effect = [
            SchemaRegistryError(404, 40401, "Subject 'orders-value' not found."),
            SchemaRegistryError(404, 40401, "Subject 'orders-value' not found."),
            SimpleNamespace(schema_id=7, version=3),
        ]
        app = self.registry_app()
        async with app.run_test(size=(120, 40)) as pilot:
            with self.assertLogs("kaskade", level="WARNING"):
                await pilot.pause()
                await app.workers.wait_for_complete()
                await pilot.pause()
                app.query_one(TabbedContent).active = "value-tab"
                app.query_one("#value-content", TextArea).load_text('{"name": "Ada"}')
                await pilot.pause()
                subtitle = str(self.composer(app).frame.border_subtitle)
                self.assertIn("Subject 'orders-value' not found", subtitle)
                self.assertIn("…", self.cell(app, "schema-schema"))

                await pilot.press("ctrl+s")
                await app.workers.wait_for_complete()
                await pilot.pause()
                self.service.produce.assert_not_called()

            await pilot.press("ctrl+s")
            await app.workers.wait_for_complete()
            await pilot.pause()

            self.service.produce.assert_called_once()
            self.assertIn("orders-value", self.cell(app, "schema-schema"))


if __name__ == "__main__":
    unittest.main()
