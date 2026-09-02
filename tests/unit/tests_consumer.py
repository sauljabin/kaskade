import asyncio
import json
import struct
import unittest
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from confluent_kafka.serialization import MessageField
from rich.text import Text
from textual import events
from textual.coordinate import Coordinate
from textual.widgets import DataTable

from kaskade.colors import NULL as NULL_STYLE
from kaskade.colors import WARNING as WARNING_STYLE
from kaskade.consumer import (
    KaskadeConsumer,
    ListRecords,
    RecordDataTable,
    TopicScreen,
    deliver_record,
    record_json,
    record_json_renderable,
)
from kaskade.deserializers import (
    BooleanDeserializer,
    BytesEncoding,
    Deserialization,
    DeserializationError,
    DeserializationResult,
    Deserializer,
    RegistrySchema,
    StringDeserializer,
)
from kaskade.help import HelpScreen
from kaskade.models import Header, Record
from kaskade.record_export import record_filename
from kaskade.themes import KaskadeApp
from kaskade.unicodes import WARNING as WARNING_INDICATOR
from kaskade.widgets import KaskadeScrollableContainer, TableFrame


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
        timestamp=datetime(2026, 8, 28, 14, 12, 5, 120_000, tzinfo=timezone.utc),
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
                "timestamp": "2026-08-28T14:12:05.120Z",
                "headers": [
                    {"key": "source", "value": "storefront"},
                    {"key": "source", "value": "mobile"},
                ],
                "key": {
                    "content": "order-1048",
                    "deserializer": {"type": "STRING"},
                },
                "value": {
                    "content": {
                        "status": "paid",
                        "customer": "Zoë",
                        "binary": b"\xff",
                    },
                    "deserializer": {"type": "JSON"},
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
            '  "key": {\n    "content": "order-1048",\n    "deserializer": {\n'
            '      "type": "STRING"\n    }\n  }',
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
        self.assertIsNone(data["timestamp"])
        self.assertIsNone(data["key"]["content"])
        self.assertIsNone(data["value"]["content"])
        self.assertEqual(
            {"type": "STRING"},
            data["key"]["deserializer"],
        )

    def test_record_dict_preserves_tombstones_and_repeated_headers(self) -> None:
        string_deserializer = StringDeserializer()
        record = Record(
            topic="orders",
            partition=2,
            offset=44,
            headers=[
                Header("trace-id", b"first", string_deserializer),
                Header("trace-id", b"second", string_deserializer),
            ],
            key_deserialization=Deserialization.STRING,
            value_deserialization=Deserialization.JSON,
        )

        self.assertEqual(
            {
                "topic": "orders",
                "partition": 2,
                "offset": 44,
                "timestamp": None,
                "headers": [
                    {"key": "trace-id", "value": "first"},
                    {"key": "trace-id", "value": "second"},
                ],
                "key": {
                    "content": None,
                    "deserializer": {"type": "STRING"},
                },
                "value": {
                    "content": None,
                    "deserializer": {"type": "JSON"},
                },
            },
            record.dict(),
        )

    def test_record_dict_uses_the_requested_deserializer_type(self) -> None:
        for deserialization in Deserialization:
            with self.subTest(deserialization=deserialization):
                data = Record(key_deserialization=deserialization).dict()

                self.assertEqual(
                    deserialization.name,
                    data["key"]["deserializer"]["type"],
                )

    def test_record_dict_preserves_deserialization_warning_metadata(self) -> None:
        key_deserializer = MagicMock()
        key_deserializer.deserialize.side_effect = DeserializationError("malformed key")
        record = Record(
            topic="orders",
            partition=1,
            offset=10,
            timestamp=datetime(2026, 8, 28, 14, 12, 7, 120_000, tzinfo=timezone.utc),
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
                "topic": "orders",
                "partition": 1,
                "offset": 10,
                "timestamp": "2026-08-28T14:12:07.120Z",
                "headers": [],
                "key": {
                    "content": "/w==",
                    "deserializer": {"type": "JSON"},
                    "error": {
                        "message": "malformed key",
                        "fallback": {"type": "BYTES", "encoding": "BASE64"},
                    },
                },
                "value": {
                    "content": "paid",
                    "deserializer": {"type": "STRING"},
                },
            },
            data,
        )
        self.assertTrue(record.has_deserialization_errors())
        key_deserializer.deserialize.assert_called_once()

    def test_record_dict_keeps_key_and_value_schema_metadata_independent(self) -> None:
        class MetadataDeserializer(Deserializer):
            def __init__(self, content: object, schema: RegistrySchema):
                self.content = content
                self.schema = schema

            def deserialize(
                self,
                data: bytes,
                topic: str | None = None,
                context: MessageField = MessageField.NONE,
            ) -> object:
                return self.content

            def deserialize_with_metadata(
                self,
                data: bytes,
                topic: str | None = None,
                context: MessageField = MessageField.NONE,
            ) -> DeserializationResult:
                return DeserializationResult(self.content, self.schema)

        record = Record(
            topic="orders",
            partition=0,
            offset=43,
            timestamp=datetime(2026, 8, 28, 14, 12, 6, 120_000, tzinfo=timezone.utc),
            key=b"key",
            value=b"value",
            key_deserialization=Deserialization.REGISTRY,
            value_deserialization=Deserialization.REGISTRY,
            key_deserializer=MetadataDeserializer(
                {"id": "order-1049"},
                RegistrySchema(12, "orders-key", 2, "AVRO"),
            ),
            value_deserializer=MetadataDeserializer(
                {"status": "shipped"},
                RegistrySchema(27, "orders-value", 5, "JSON"),
            ),
        )

        data = record.dict()

        self.assertEqual(
            {
                "topic": "orders",
                "partition": 0,
                "offset": 43,
                "timestamp": "2026-08-28T14:12:06.120Z",
                "headers": [],
                "key": {
                    "content": {"id": "order-1049"},
                    "deserializer": {
                        "type": "REGISTRY",
                        "schema": {
                            "id": 12,
                            "subject": "orders-key",
                            "version": 2,
                            "type": "AVRO",
                        },
                    },
                },
                "value": {
                    "content": {"status": "shipped"},
                    "deserializer": {
                        "type": "REGISTRY",
                        "schema": {
                            "id": 27,
                            "subject": "orders-value",
                            "version": 5,
                            "type": "JSON",
                        },
                    },
                },
            },
            data,
        )

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
    def test_consumer_passes_bytes_and_fallback_configs_independently(
        self, consumer_service: MagicMock
    ) -> None:
        consumer_service.return_value.consume = AsyncMock(return_value=[])

        KaskadeConsumer(
            "orders",
            {},
            {},
            {},
            {},
            Deserialization.BYTES,
            Deserialization.STRING,
            bytes_config={"key.encoding": "hex"},
            fallback_config={"encoding": "python"},
        )

        self.assertEqual(
            {"key.encoding": "hex"},
            consumer_service.call_args.kwargs["bytes_config"],
        )
        self.assertEqual(
            {"encoding": "python"},
            consumer_service.call_args.kwargs["fallback_config"],
        )

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
            help_bindings = {
                binding.description: binding.keys for binding in app.screen.help_bindings
            }
            self.assertEqual(("^e",), help_bindings["Export Record"])
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


class TestRecordDetailsNavigation(unittest.IsolatedAsyncioTestCase):
    @patch("kaskade.consumer.ConsumerService")
    async def test_navigates_records_without_closing_details_and_keeps_selection(
        self, consumer_service: MagicMock
    ) -> None:
        consumed_records = [
            Record(topic="orders", partition=0, offset=offset) for offset in range(3)
        ]
        consumer_service.return_value.consume = AsyncMock(return_value=consumed_records)
        app = KaskadeConsumer(
            "orders",
            {},
            {},
            {},
            {},
            Deserialization.STRING,
            Deserialization.JSON,
        )

        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = app.query_one(RecordDataTable)

            await pilot.press("enter")
            await pilot.pause()
            details = app.screen
            self.assertIsInstance(details, TopicScreen)
            self.assertIs(consumed_records[0], details.record)
            self.assertFalse(details.check_action("previous_record", ()))
            self.assertTrue(details.check_action("next_record", ()))

            record_json_widget = details.query_one(".record-json")
            with patch.object(
                record_json_widget,
                "update",
                wraps=record_json_widget.update,
            ) as update_record_json:
                await pilot.press("n", "n")
            self.assertIs(details, app.screen)
            self.assertIs(consumed_records[2], details.record)
            self.assertEqual(2, details.data["offset"])
            rendered_record = update_record_json.call_args.args[0]
            self.assertEqual(
                record_json(consumed_records[2]).rstrip("\n"),
                rendered_record.text.plain,
            )
            self.assertEqual(
                "[primary]Record[/primary] "
                "[[primary]orders[/primary]]"
                "[[primary]0[/primary]]"
                "[[primary]2[/primary]]",
                details.query_one(KaskadeScrollableContainer).border_title,
            )
            self.assertTrue(details.check_action("previous_record", ()))
            self.assertFalse(details.check_action("next_record", ()))

            await pilot.press("N")
            self.assertIs(consumed_records[1], details.record)

            await pilot.press("p", "n")
            self.assertIs(consumed_records[1], details.record)

            await pilot.press("escape")
            await pilot.pause()
            self.assertIs(consumed_records[1], app.query_one(ListRecords).current_record)
            self.assertEqual(1, table.cursor_row)


class TestConsumptionCoordination(unittest.IsolatedAsyncioTestCase):
    @patch("kaskade.consumer.ConsumerService")
    async def test_keeps_records_frame_visible_while_table_loads(
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

        async with app.run_test() as pilot:
            try:
                await started.wait()
                await pilot.pause()
                frame = app.query_one("#records-frame", TableFrame)
                table = app.query_one("#records-table", DataTable)

                self.assertTrue(table.loading)
                self.assertFalse(frame.loading)
                self.assertIn("Records", frame.border_title)
                self.assertNotEqual("", frame.styles.border_top[0])
                self.assertEqual("", table.styles.border_top[0])
            finally:
                release.set()
            await app.workers.wait_for_complete()

    @patch("kaskade.consumer.ConsumerService")
    async def test_boolean_cells_use_json_literals(self, consumer_service: MagicMock) -> None:
        deserializer = BooleanDeserializer()
        record = Record(
            topic="boolean",
            key=struct.pack(">?", False),
            value=struct.pack(">?", True),
            key_deserialization=Deserialization.BOOLEAN,
            value_deserialization=Deserialization.BOOLEAN,
            key_deserializer=deserializer,
            value_deserializer=deserializer,
        )
        consumer_service.return_value.consume = AsyncMock(return_value=[record])
        app = KaskadeConsumer(
            "boolean",
            {},
            {},
            {},
            {},
            Deserialization.BOOLEAN,
            Deserialization.BOOLEAN,
        )

        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            row = app.query_one(RecordDataTable).get_row_at(0)

            self.assertEqual(["false", "true"], row[:2])

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
            fallback_bytes_encoding=BytesEncoding.HEX,
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
            table = app.query_one(RecordDataTable)
            row = table.get_row_at(0)

            self.assertIsInstance(row[0], Text)
            self.assertEqual(
                f"{WARNING_INDICATOR} ff",
                row[0].plain,
            )
            self.assertEqual(WARNING_STYLE, row[0].style)
            self.assertEqual("paid", row[1])

            table.hover_coordinate = Coordinate(0, 0)
            await pilot.pause()

            self.assertIsInstance(table.tooltip, Text)
            self.assertIn("Key Deserialization Warning", table.tooltip.plain)
            self.assertIn("Record: orders[1][10]", table.tooltip.plain)
            self.assertIn("Requested: JSON", table.tooltip.plain)
            self.assertIn("Fallback: BYTES", table.tooltip.plain)
            self.assertIn("Encoding: HEX", table.tooltip.plain)
            self.assertIn("Error: malformed key", table.tooltip.plain)

            table.hover_coordinate = Coordinate(0, 1)
            await pilot.pause()

            self.assertIsNone(table.tooltip)

    @patch("kaskade.consumer.ConsumerService")
    async def test_null_key_and_value_have_colored_cells_and_tooltips(
        self, consumer_service: MagicMock
    ) -> None:
        record = Record(
            topic="orders",
            partition=2,
            offset=44,
            key_deserialization=Deserialization.STRING,
            value_deserialization=Deserialization.JSON,
        )
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

        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = app.query_one(RecordDataTable)
            row = table.get_row_at(0)

            for cell in row[:2]:
                self.assertIsInstance(cell, Text)
                self.assertEqual("null", cell.plain)
                self.assertEqual(NULL_STYLE, cell.style)

            table.hover_coordinate = Coordinate(0, 0)
            await pilot.pause()

            self.assertIsInstance(table.tooltip, Text)
            self.assertIn("Null Key", table.tooltip.plain)
            self.assertIn("This Kafka record has no key", table.tooltip.plain)
            self.assertEqual(WARNING_STYLE, table.tooltip.spans[0].style)

            table.hover_coordinate = Coordinate(0, 1)
            await pilot.pause()

            self.assertIsInstance(table.tooltip, Text)
            self.assertIn("Null Value", table.tooltip.plain)
            self.assertIn("This Kafka record is a tombstone", table.tooltip.plain)
            self.assertEqual(WARNING_STYLE, table.tooltip.spans[0].style)

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
