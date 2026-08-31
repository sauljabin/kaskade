import asyncio
import json
import unittest
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from rich.text import Text
from textual import events
from textual.widgets import DataTable

from kaskade.colors import WARNING as WARNING_STYLE
from kaskade.consumer import (
    KaskadeConsumer,
    ListRecords,
    TopicScreen,
    deliver_record,
    record_json,
    record_json_renderable,
)
from kaskade.deserializers import Deserialization, DeserializationError, StringDeserializer
from kaskade.help import HelpScreen
from kaskade.models import Header, Record
from kaskade.record_export import record_filename
from kaskade.themes import KaskadeApp
from kaskade.unicodes import WARNING as WARNING_INDICATOR


def exported_record() -> Record:
    value_deserializer = MagicMock()
    value_deserializer.deserialize.return_value = {
        "status": "paid",
        "customer": "Zoë",
        "binary": b"\xff",
    }
    string_deserializer = StringDeserializer()
    return Record(
        topic="orders",
        partition=2,
        offset=42,
        date="2026-08-28 14:12:05.120",
        headers=[
            Header("source", b"storefront", string_deserializer),
            Header("source", b"mobile", string_deserializer),
        ],
        key=b"order-1048",
        value=b"payload",
        key_deserialization=Deserialization.STRING,
        value_deserialization=Deserialization.JSON,
        key_deserializer=string_deserializer,
        value_deserializer=value_deserializer,
    )


class TestRecordExport(unittest.TestCase):
    def test_record_dict_contains_complete_nested_export_contract(self) -> None:
        record = exported_record()

        self.assertEqual(
            {
                "topic": "orders",
                "partition": 2,
                "offset": 42,
                "date": "2026-08-28 14:12:05.120",
                "headers": [("source", "storefront"), ("source", "mobile")],
                "key": {"deserializer": "STRING", "content": "order-1048"},
                "value": {
                    "deserializer": "JSON",
                    "content": {
                        "status": "paid",
                        "customer": "Zoë",
                        "binary": b"\xff",
                    },
                },
            },
            record.dict(),
        )

    def test_record_json_is_readable_utf8_and_stringifies_unsupported_values(self) -> None:
        exported = record_json(exported_record())

        self.assertTrue(exported.endswith("\n"))
        self.assertIn("Zoë", exported)
        self.assertEqual(
            "b'\\xff'",
            json.loads(exported)["value"]["content"]["binary"],
        )

    def test_record_json_renderable_expands_nested_objects_and_wraps_long_values(self) -> None:
        renderable = record_json_renderable(exported_record().dict())

        self.assertEqual(record_json(exported_record()).rstrip("\n"), renderable.text.plain)
        self.assertIn(
            '  "key": {\n    "deserializer": "STRING",\n    "content": "order-1048"\n  }',
            renderable.text.plain,
        )
        self.assertFalse(renderable.text.no_wrap)
        self.assertEqual("fold", renderable.text.overflow)

    def test_record_dict_preserves_empty_headers_and_null_content(self) -> None:
        data = Record(
            topic="empty",
            partition=0,
            offset=0,
            key_deserialization=Deserialization.STRING,
            value_deserialization=Deserialization.JSON,
        ).dict()

        self.assertEqual([], data["headers"])
        self.assertIsNone(data["key"]["content"])
        self.assertIsNone(data["value"]["content"])

    def test_record_dict_preserves_deserialization_warning_metadata(self) -> None:
        key_deserializer = MagicMock()
        key_deserializer.deserialize.side_effect = DeserializationError("malformed key")
        record = Record(
            topic="orders",
            partition=1,
            offset=10,
            key=b"\xff",
            value=b"paid",
            key_deserialization=Deserialization.JSON,
            value_deserialization=Deserialization.STRING,
            key_deserializer=key_deserializer,
            value_deserializer=StringDeserializer(),
        )

        data = record.dict()

        self.assertEqual(
            {
                "deserializer": "JSON",
                "fallback": "BYTES",
                "content": "b'\\xff'",
                "error": "malformed key",
            },
            data["key"],
        )
        self.assertEqual(
            {"deserializer": "STRING", "content": "paid"},
            data["value"],
        )
        self.assertTrue(record.has_deserialization_errors())
        key_deserializer.deserialize.assert_called_once()

    def test_record_filename_contains_identity_and_sanitized_export_time(self) -> None:
        record = Record(topic="orders.v1:archive", partition=2, offset=42)

        filename = record_filename(
            record,
            datetime(2026, 8, 28, 14, 20, 10, 930643, tzinfo=timezone.utc),
        )

        self.assertEqual(
            "kaskade-record-orders_v1_archive-2-42_2026-08-28T14_20_10_930643.json",
            filename,
        )

    def test_delivery_uses_screenshot_destination_and_json_metadata(self) -> None:
        application = MagicMock()

        deliver_record(application, exported_record())

        application.deliver_text.assert_called_once()
        content = application.deliver_text.call_args.args[0]
        options = application.deliver_text.call_args.kwargs
        self.assertIsInstance(content, StringIO)
        self.assertEqual("orders", json.loads(content.getvalue())["topic"])
        self.assertNotIn("save_directory", options)
        self.assertEqual("utf-8", options["encoding"])
        self.assertEqual("application/json", options["mime_type"])
        self.assertEqual("record", options["name"])

    def test_successful_delivery_notifies_with_the_saved_path(self) -> None:
        application = KaskadeApp()
        application.notify = MagicMock()
        export_path = Path("/downloads/record.json")

        application.on_record_delivery_complete(
            events.DeliveryComplete("delivery-key", export_path, "record")
        )

        application.notify.assert_called_once_with(
            f"Saved record to [$text-success]{str(export_path)!r}",
            title="Record Export",
        )

    def test_browser_delivery_notifies_without_a_path(self) -> None:
        application = KaskadeApp()
        application.notify = MagicMock()

        application.on_record_delivery_complete(
            events.DeliveryComplete("delivery-key", name="record")
        )

        application.notify.assert_called_once_with("Saved record", title="Record Export")

    def test_failed_delivery_notifies_as_an_error(self) -> None:
        application = KaskadeApp()
        application.notify = MagicMock()

        application.on_record_delivery_failed(
            events.DeliveryFailed("delivery-key", OSError("disk full"), "record")
        )

        application.notify.assert_called_once_with(
            "Failed to save record",
            title="Record Export",
            severity="error",
        )


class TestRecordExportActions(unittest.IsolatedAsyncioTestCase):
    @patch("kaskade.consumer.ConsumerService")
    async def test_ctrl_e_exports_from_table_and_record_details(
        self, consumer_service: MagicMock
    ) -> None:
        record = exported_record()
        consumer_service.return_value.consume = AsyncMock(return_value=[record])
        app = KaskadeConsumer(
            "orders",
            {},
            {},
            {},
            {},
            Deserialization.STRING,
            Deserialization.JSON,
        )
        app.deliver_text = MagicMock(return_value="delivery-key")

        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            records = app.query_one(ListRecords)

            self.assertIs(record, records.current_record)
            self.assertTrue(records.check_action("export_record", ()))
            command_titles = {command.title for command in app.get_system_commands(app.screen)}
            self.assertIn("Export Record", command_titles)
            self.assertFalse(
                next(
                    binding
                    for binding in ListRecords.BINDINGS
                    if binding.id == "kaskade.records.export"
                ).show
            )

            await pilot.press("?")
            self.assertIsInstance(app.screen, HelpScreen)
            self.assertIn(
                "Export Record",
                {binding.description for binding in app.screen.help_bindings},
            )
            await pilot.press("escape")

            await pilot.press("ctrl+e")
            app.deliver_text.assert_called_once()

            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, TopicScreen)
            self.assertFalse(
                next(
                    binding
                    for binding in TopicScreen.BINDINGS
                    if binding.id == "kaskade.records.export"
                ).show
            )
            await pilot.press("ctrl+e")
            self.assertEqual(2, app.deliver_text.call_count)

    @patch("kaskade.consumer.ConsumerService")
    async def test_table_export_is_disabled_without_a_record(
        self, consumer_service: MagicMock
    ) -> None:
        consumer_service.return_value.consume = AsyncMock(return_value=[])
        app = KaskadeConsumer(
            "orders",
            {},
            {},
            {},
            {},
            Deserialization.STRING,
            Deserialization.JSON,
        )
        app.deliver_text = MagicMock()

        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            records = app.query_one(ListRecords)

            self.assertFalse(records.check_action("export_record", ()))
            await pilot.press("ctrl+e")
            app.deliver_text.assert_not_called()


class TestRecordCopyActions(unittest.IsolatedAsyncioTestCase):
    @patch("kaskade.consumer.ConsumerService")
    async def test_y_copies_json_from_table_and_record_details(
        self, consumer_service: MagicMock
    ) -> None:
        record = exported_record()
        expected_json = record_json(record).removesuffix("\n")
        consumer_service.return_value.consume = AsyncMock(return_value=[record])
        app = KaskadeConsumer(
            "orders",
            {},
            {},
            {},
            {},
            Deserialization.STRING,
            Deserialization.JSON,
        )
        app.notify = MagicMock()

        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            records = app.query_one(ListRecords)

            self.assertTrue(records.check_action("copy_record", ()))
            self.assertIn(
                "Copy Record",
                {command.title for command in app.get_system_commands(app.screen)},
            )

            await pilot.press("y")

            self.assertEqual(expected_json, app.clipboard)
            self.assertFalse(app.clipboard.endswith("\n"))
            self.assertEqual("Zoë", json.loads(app.clipboard)["value"]["content"]["customer"])
            app.notify.assert_called_once_with(
                "Copied record JSON to clipboard",
                title="Copied",
            )

            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, TopicScreen)
            app.copy_to_clipboard("")
            app.notify.reset_mock()

            await pilot.press("y")

            self.assertEqual(expected_json, app.clipboard)
            app.notify.assert_called_once_with(
                "Copied record JSON to clipboard",
                title="Copied",
            )

    @patch("kaskade.consumer.ConsumerService")
    async def test_copy_is_disabled_without_a_record(self, consumer_service: MagicMock) -> None:
        consumer_service.return_value.consume = AsyncMock(return_value=[])
        app = KaskadeConsumer(
            "orders",
            {},
            {},
            {},
            {},
            Deserialization.STRING,
            Deserialization.JSON,
        )
        app.notify = MagicMock()

        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            records = app.query_one(ListRecords)

            self.assertFalse(records.check_action("copy_record", ()))
            await pilot.press("y")

            self.assertEqual("", app.clipboard)
            app.notify.assert_not_called()

    @patch("kaskade.consumer.ConsumerService")
    async def test_copy_reports_deserialization_errors(self, consumer_service: MagicMock) -> None:
        record = exported_record()
        consumer_service.return_value.consume = AsyncMock(return_value=[record])
        app = KaskadeConsumer(
            "orders",
            {},
            {},
            {},
            {},
            Deserialization.STRING,
            Deserialization.JSON,
        )
        app.notify = MagicMock()

        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            with patch.object(record, "dict", side_effect=ValueError("invalid payload")):
                await pilot.press("y")

            self.assertEqual("", app.clipboard)
            app.notify.assert_called_once_with(
                "invalid payload",
                severity="error",
                title="Deserialization Error",
            )


class TestConsumptionCoordination(unittest.IsolatedAsyncioTestCase):
    @patch("kaskade.consumer.ConsumerService")
    async def test_warning_record_has_visible_indicator_and_warning_cells(
        self, consumer_service: MagicMock
    ) -> None:
        key_deserializer = MagicMock()
        key_deserializer.deserialize.side_effect = DeserializationError("malformed key")
        record = Record(
            topic="orders",
            partition=1,
            offset=10,
            key=b"\xff",
            value=b"paid",
            key_deserialization=Deserialization.JSON,
            value_deserialization=Deserialization.STRING,
            key_deserializer=key_deserializer,
            value_deserializer=StringDeserializer(),
        )
        consumer_service.return_value.consume = AsyncMock(return_value=[record])
        app = KaskadeConsumer(
            "orders",
            {},
            {},
            {},
            {},
            Deserialization.JSON,
            Deserialization.STRING,
        )

        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            row = app.query_one(DataTable).get_row_at(0)

            self.assertIsInstance(row[0], Text)
            self.assertEqual(
                f"{WARNING_INDICATOR} b'\\xff'",
                row[0].plain,
            )
            self.assertEqual(WARNING_STYLE, row[0].style)
            self.assertEqual("paid", row[1])

    @patch("kaskade.consumer.ConsumerService")
    async def test_duplicate_requests_do_not_schedule_overlapping_consumers(
        self, consumer_service: MagicMock
    ) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def consume(*, filters: object) -> list[Record]:
            started.set()
            await release.wait()
            return []

        consumer_service.return_value.consume = AsyncMock(side_effect=consume)
        consumer_service.return_value.aclose = AsyncMock()
        app = KaskadeConsumer(
            "orders",
            {},
            {},
            {},
            {},
            Deserialization.STRING,
            Deserialization.JSON,
        )

        async with app.run_test():
            await started.wait()
            records = app.query_one(ListRecords)

            records.action_consume()
            records.action_consume()

            self.assertEqual(1, consumer_service.return_value.consume.call_count)
            release.set()
            await app.workers.wait_for_complete()


if __name__ == "__main__":
    unittest.main()
