import asyncio
import json
import struct
import unittest
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

from confluent_kafka.serialization import MessageField
from rich.text import Text
from textual import events
from textual.color import Color
from textual.containers import Container, Grid
from textual.coordinate import Coordinate
from textual.widgets import DataTable, OptionList, Static, Tab, TabbedContent, TabPane, Tabs

from kaskade.colors import NULL as NULL_STYLE
from kaskade.colors import WARNING as WARNING_STYLE
from kaskade.configs import CONFLUENT
from kaskade.consumer import (
    KaskadeConsumer,
    ListRecords,
    RecordDataTable,
    RecordFieldDetails,
    TopicScreen,
    deliver_record,
    format_payload_size,
    record_json,
    record_json_renderable,
    record_payload_size,
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
from kaskade.record_export import readable_json, record_filename
from kaskade.themes import KaskadeApp
from kaskade.unicodes import WARNING as WARNING_INDICATOR
from kaskade.widgets import KaskadeScrollableContainer, TableFrame


class TestPayloadSizeFormatting(unittest.TestCase):
    def test_formats_kilobytes_and_megabytes(self) -> None:
        self.assertEqual("—", format_payload_size(None))
        self.assertEqual("0.00 KB", format_payload_size(0))
        self.assertEqual("0.001 KB", format_payload_size(1))
        self.assertEqual("1.00 KB", format_payload_size(1_000))
        self.assertEqual("1000.00 KB", format_payload_size(999_999))
        self.assertEqual("1.00 MB", format_payload_size(1_000_000))
        self.assertEqual("2.50 MB", format_payload_size(2_500_000))

    def test_totals_raw_record_payloads_and_header_names(self) -> None:
        record = Record(
            key=b"key",
            value=b"value",
            headers=[Header("source", b"mobile"), Header("empty", None)],
        )

        self.assertEqual(25, record_payload_size(record))


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
                    "deserializer": "STRING",
                },
                "value": {
                    "content": {
                        "status": "paid",
                        "customer": "Zoë",
                        "binary": b"\xff",
                    },
                    "deserializer": "JSON",
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
            '  "key": {\n    "content": "order-1048",\n' '    "deserializer": "STRING"\n  }',
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
        self.assertEqual("STRING", data["key"]["deserializer"])

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
                    "deserializer": "STRING",
                },
                "value": {
                    "content": None,
                    "deserializer": "JSON",
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
                    data["key"]["deserializer"],
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
                    "deserializer": "JSON",
                    "error": {
                        "message": "malformed key",
                        "fallback": "BYTES",
                        "encoding": "BASE64",
                    },
                },
                "value": {
                    "content": "paid",
                    "deserializer": "STRING",
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
                    "deserializer": "REGISTRY",
                    "schema": {
                        "provider": CONFLUENT,
                        "id": 12,
                        "subject": "orders-key",
                        "version": 2,
                        "type": "AVRO",
                    },
                },
                "value": {
                    "content": {"status": "shipped"},
                    "deserializer": "REGISTRY",
                    "schema": {
                        "provider": CONFLUENT,
                        "id": 27,
                        "subject": "orders-value",
                        "version": 5,
                        "type": "JSON",
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
            fallback_config={"encoding": "escaped"},
        )

        self.assertEqual(
            {"key.encoding": "hex"},
            consumer_service.call_args.kwargs["bytes_config"],
        )
        self.assertEqual(
            {"encoding": "escaped"},
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
            app.screen.query_one(TabbedContent).active = "value"
            self.assertFalse(
                next(
                    binding
                    for binding in TopicScreen.BINDINGS
                    if binding.id == "kaskade.records.export"
                ).show
            )
            await pilot.press("ctrl+e")
            self.assertEqual(2, app.deliver_text.call_count)
            delivered_content = app.deliver_text.call_args.args[0]
            self.assertEqual(record_json(record), delivered_content.getvalue())

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
    async def test_y_copies_json_from_table_and_active_record_details_tab(
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
            tabs = app.screen.query_one(TabbedContent)
            record_data = record.dict()
            expected_copies = (
                ("key", record_data["key"], "record key"),
                ("value", record_data["value"], "record value"),
                ("headers", record_data["headers"], "record headers"),
                ("json", record_data, "record JSON"),
            )
            for active, data, description in expected_copies:
                with self.subTest(active=active):
                    tabs.active = active
                    await pilot.pause()
                    app.copy_to_clipboard("")
                    app.notify.reset_mock()

                    await pilot.press("y")

                    self.assertEqual(readable_json(data), app.clipboard)
                    app.notify.assert_called_once_with(
                        f"Copied {description} to clipboard",
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


class TestRecordDetailsTabs(unittest.IsolatedAsyncioTestCase):
    async def test_content_scrolls_independently_of_field_metadata(self) -> None:
        payload = ("long field content " * 200).encode()
        record = Record(
            topic="orders",
            key=payload,
            value=b"\xff" + payload,
            key_deserialization=Deserialization.STRING,
            value_deserialization=Deserialization.STRING,
            key_deserializer=StringDeserializer(),
            value_deserializer=StringDeserializer(),
            headers=[
                Header("long-header", payload, StringDeserializer()),
                Header("short-header", b"short", StringDeserializer()),
            ],
        )
        for theme in ("eva01-berserk", "eva01", "textual-light", "ansi-light"):
            for size in ((140, 40), (60, 24)):
                with self.subTest(theme=theme, size=size):
                    app = KaskadeApp()
                    app.theme = theme
                    async with app.run_test(size=size) as pilot:
                        details = TopicScreen(record)
                        await app.push_screen(details)
                        for tab_id in ("key", "value", "headers"):
                            details.query_one(Tabs).focus()
                            details.query_one(TabbedContent).active = tab_id
                            await pilot.pause()
                            field = details.query_one(f"#{tab_id} RecordFieldDetails")
                            metadata = field.query_one(".record-field-metadata")
                            scroll = field.query_one(
                                ".record-content-scroll", KaskadeScrollableContainer
                            )
                            diagnostics_region = field.query_one(".record-diagnostics").region
                            self.assertGreater(scroll.content_region.height, 0)
                            self.assertLessEqual(scroll.region.bottom, field.region.bottom)
                            self.assertEqual(
                                field.query_one(".record-content-area").region.height,
                                scroll.region.height,
                            )
                            self.assertTrue(scroll.show_vertical_scrollbar)
                            self.assertFalse(scroll.show_horizontal_scrollbar)
                            self.assertLessEqual(
                                scroll.virtual_size.width, scroll.scrollable_content_region.width
                            )
                            self.assertFalse(field.show_vertical_scrollbar)
                            self.assertEqual(
                                Color.parse(app.get_css_variables()["panel-darken-1"]),
                                scroll.styles.background,
                            )
                            self.assertEqual(
                                (1, 2, 1, 2), field.query_one(".record-content").styles.padding
                            )
                            scroll.focus()
                            await pilot.press("G")
                            await pilot.pause()
                            self.assertGreater(scroll.scroll_y, 0)
                            self.assertEqual(0, metadata.scroll_y)
                            self.assertEqual(
                                diagnostics_region, field.query_one(".record-diagnostics").region
                            )
                            if tab_id == "value":
                                self.assertTrue(field.query_one(".record-error").display)
                        headers = details.query_one("#record-headers-list", OptionList)
                        headers.focus()
                        headers.highlighted = 1
                        await pilot.pause()
                        self.assertEqual(0, scroll.scroll_y)
                        content_height = field.query_one(".record-content").region.height
                        available_height = field.query_one(".record-content-area").region.height
                        self.assertEqual(
                            min(content_height, available_height), scroll.region.height
                        )
                        self.assertEqual(
                            content_height > available_height, scroll.show_vertical_scrollbar
                        )
                        self.assertFalse(scroll.show_horizontal_scrollbar)
                        if size[0] == 140:
                            self.assertLess(scroll.region.height, available_height)

    @patch("kaskade.consumer.ConsumerService")
    async def test_displays_ordered_headers_and_complete_field_diagnostics(
        self, consumer_service: MagicMock
    ) -> None:
        class MetadataDeserializer(Deserializer):
            def deserialize(
                self,
                data: bytes,
                topic: str | None = None,
                context: MessageField = MessageField.NONE,
            ) -> object:
                return {"status": "paid"}

            def deserialize_with_metadata(
                self,
                data: bytes,
                topic: str | None = None,
                context: MessageField = MessageField.NONE,
            ) -> DeserializationResult:
                return DeserializationResult(
                    {"status": "paid"},
                    RegistrySchema(27, "orders-value", 5, "JSON"),
                )

        failing_header_deserializer = MagicMock()
        failing_header_deserializer.deserialize.side_effect = DeserializationError("invalid UTF-8")
        record = Record(
            topic="orders",
            partition=2,
            offset=42,
            timestamp=datetime(2026, 8, 28, 14, 12, 5, 120_000, tzinfo=timezone.utc),
            headers=[
                Header("source", b"storefront", StringDeserializer()),
                Header(
                    "source",
                    b"\xff",
                    failing_header_deserializer,
                    BytesEncoding.HEX,
                ),
            ],
            key=b"\xff",
            value=b"payload",
            key_deserialization=Deserialization.BYTES,
            value_deserialization=Deserialization.REGISTRY,
            value_deserializer=MetadataDeserializer(),
            key_bytes_encoding=BytesEncoding.HEX,
        )
        consumer_service.return_value.consume = AsyncMock(return_value=[])
        app = KaskadeConsumer(
            "orders",
            {},
            {},
            {},
            {},
            Deserialization.BYTES,
            Deserialization.REGISTRY,
        )

        async with app.run_test() as pilot:
            app.push_screen(TopicScreen(record))
            await pilot.pause()
            details = app.screen
            tabs = details.query_one(TabbedContent)
            headers = details.query_one("#record-headers-list", OptionList)

            self.assertEqual("key", tabs.active)
            self.assertEqual(
                "[primary]Record Details[/primary] [[primary]orders[/primary]]"
                "[[primary]2[/primary]][[primary]42[/primary]]",
                details.query_one(".record-details", Container).border_title,
            )
            self.assertEqual(
                4,
                details.query_one("#record-metadata", Grid).styles.grid_size_columns,
            )
            self.assertEqual(
                ["Key", "Value", "Headers [2]", "Export"],
                [tab.label_text for tab in details.query(Tab)],
            )
            self.assertEqual(
                ["source", "source"],
                [
                    str(headers.get_option_at_index(index).prompt)
                    for index in range(headers.option_count)
                ],
            )
            self.assertEqual(
                "TOTAL SIZE\n0.03 KB",
                details.query_one("#record-total-size", Static).render().plain,
            )
            total_size_content = details.query_one("#record-total-size", Static).content
            self.assertIsInstance(total_size_content, Text)
            self.assertEqual("muted", total_size_content.spans[0].style)
            self.assertEqual(
                "PARTITION\n2",
                details.query_one("#record-partition", Static).render().plain,
            )
            self.assertEqual(
                "OFFSET\n42",
                details.query_one("#record-offset", Static).render().plain,
            )
            self.assertEqual(
                f"TIMESTAMP\n{record.timestamp_str()}",
                details.query_one("#record-timestamp", Static).render().plain,
            )

            headers.highlighted = 1
            await pilot.pause()
            header_details = details.query_one("#record-header-details", RecordFieldDetails)
            self.assertEqual(
                "HEADER\nsource",
                header_details.query_one(".record-field-name", Static).render().plain,
            )
            self.assertEqual(
                "DESERIALIZER\nSTRING",
                header_details.query_one(".record-deserializer", Static).render().plain,
            )
            deserializer_content = header_details.query_one(".record-deserializer", Static).content
            self.assertIsInstance(deserializer_content, Text)
            self.assertEqual("muted", deserializer_content.spans[0].style)
            self.assertEqual(
                "SIZE\n0.001 KB",
                header_details.query_one(".record-size", Static).render().plain,
            )
            error = header_details.query_one(".record-error", Static)
            self.assertTrue(error.display)
            self.assertIn("ERROR\ninvalid UTF-8\nFallback: BYTES · HEX", error.render().plain)
            self.assertEqual("solid", error.styles.border_top[0])
            self.assertGreater(error.styles.border_top[1].r, error.styles.border_top[1].g)
            self.assertGreater(error.styles.background.a, 0)
            self.assertEqual(
                "FALLBACK CONTENT",
                header_details.query_one(".record-content-label", Static).render().plain,
            )
            self.assertEqual(
                '"ff"',
                header_details.query_one(".record-content", Static).content.text.plain,
            )

            headers.highlighted = 0
            await pilot.pause()
            self.assertFalse(header_details.query_one(".record-error", Static).display)
            self.assertEqual(
                "SIZE\n0.01 KB",
                header_details.query_one(".record-size", Static).render().plain,
            )
            self.assertEqual(
                "CONTENT",
                header_details.query_one(".record-content-label", Static).render().plain,
            )
            self.assertEqual(
                '"storefront"',
                header_details.query_one(".record-content", Static).content.text.plain,
            )

            tabs.active = "key"
            await pilot.pause()
            key_details = details.query_one("#record-key-details", RecordFieldDetails)
            self.assertEqual(
                "DESERIALIZER\nBYTES · HEX",
                key_details.query_one(".record-deserializer", Static).render().plain,
            )
            self.assertEqual(
                "SIZE\n0.001 KB",
                key_details.query_one(".record-size", Static).render().plain,
            )
            self.assertFalse(key_details.query_one(".record-error", Static).display)
            self.assertEqual(
                "CONTENT",
                key_details.query_one(".record-content-label", Static).render().plain,
            )
            self.assertEqual(
                '"ff"',
                key_details.query_one(".record-content", Static).content.text.plain,
            )

            tabs.active = "value"
            await pilot.pause()
            value_details = details.query_one("#record-value-details", RecordFieldDetails)
            self.assertEqual(
                "DESERIALIZER\nREGISTRY · JSON",
                value_details.query_one(".record-deserializer", Static).render().plain,
            )
            diagnostics = list(value_details.query(".record-diagnostic"))
            self.assertEqual(3, len(diagnostics))
            diagnostic_heights = {diagnostic.region.height for diagnostic in diagnostics}
            self.assertEqual(1, len(diagnostic_heights))
            self.assertEqual(
                "SCHEMA\nConfluent · ID 27 · orders-value v5",
                value_details.query_one(".record-schema", Static).render().plain,
            )
            self.assertEqual(
                "SIZE\n0.007 KB",
                value_details.query_one(".record-size", Static).render().plain,
            )
            self.assertIn(
                '"status": "paid"',
                value_details.query_one(".record-content", Static).content.text.plain,
            )

            tabs.active = "json"
            await pilot.pause()
            self.assertEqual(
                record_json(record).rstrip("\n"),
                details.query_one(".record-json", Static).content.text.plain,
            )


class TestRecordDetailsNavigation(unittest.IsolatedAsyncioTestCase):
    @patch("kaskade.consumer.ConsumerService")
    async def test_navigates_records_without_closing_details_and_keeps_selection(
        self, consumer_service: MagicMock
    ) -> None:
        consumed_records = [
            Record(
                topic="orders",
                partition=0,
                offset=0,
                headers=[
                    Header("trace-id", b"second", StringDeserializer()),
                    Header("trace-id", b"first", StringDeserializer()),
                ],
            ),
            Record(topic="orders", partition=0, offset=1),
            Record(
                topic="orders",
                partition=0,
                offset=2,
                headers=[Header("source", b"mobile", StringDeserializer())],
            ),
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
            tabs = details.query_one(TabbedContent)
            tabs.active = "value"
            await pilot.pause()

            record_json_widget = details.query_one(".record-json")
            value_scroll = details.query_one("#value", TabPane).query_one(".record-detail-scroll")
            with (
                patch.object(
                    record_json_widget,
                    "update",
                    wraps=record_json_widget.update,
                ) as update_record_json,
                patch.object(
                    value_scroll,
                    "scroll_home",
                    wraps=value_scroll.scroll_home,
                ) as scroll_value_home,
                patch.object(
                    table,
                    "refresh",
                    wraps=table.refresh,
                ) as refresh_table,
            ):
                await pilot.press("n", "n")
            self.assertIs(details, app.screen)
            self.assertIs(consumed_records[2], details.record)
            self.assertEqual(2, details.data["offset"])
            self.assertEqual(2, table.cursor_row)
            self.assertEqual("value", tabs.active)
            scroll_value_home.assert_called_with(animate=False)
            self.assertIn(call(), refresh_table.call_args_list)
            self.assertIs(consumed_records[2], app.query_one(ListRecords).current_record)
            rendered_record = update_record_json.call_args.args[0]
            self.assertEqual(
                record_json(consumed_records[2]).rstrip("\n"),
                rendered_record.text.plain,
            )
            self.assertEqual(
                "OFFSET\n2",
                details.query_one("#record-offset", Static).render().plain,
            )
            self.assertEqual(
                "TOTAL SIZE\n0.01 KB",
                details.query_one("#record-total-size", Static).render().plain,
            )
            self.assertEqual(
                ["Key", "Value", "Headers [1]", "Export"],
                [tab.label_text for tab in details.query(Tab)],
            )
            header_list = details.query_one("#record-headers-list", OptionList)
            self.assertEqual(1, header_list.option_count)
            self.assertEqual(0, header_list.highlighted)
            self.assertTrue(details.check_action("previous_record", ()))
            self.assertFalse(details.check_action("next_record", ()))

            await pilot.press("N")
            self.assertIs(consumed_records[1], details.record)
            self.assertEqual(1, table.cursor_row)
            self.assertEqual(
                "TOTAL SIZE\n0.00 KB",
                details.query_one("#record-total-size", Static).render().plain,
            )
            self.assertFalse(header_list.display)
            self.assertTrue(details.query_one("#record-headers-empty", Static).display)
            value_details = details.query_one("#record-value-details", RecordFieldDetails)
            self.assertEqual(
                "null",
                value_details.query_one(".record-content", Static).content.text.plain,
            )
            self.assertEqual(
                "SIZE\n—",
                value_details.query_one(".record-size", Static).render().plain,
            )

            await pilot.press("p", "n")
            self.assertIs(consumed_records[1], details.record)
            self.assertEqual(1, table.cursor_row)

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

            self.assertEqual("renderable", table.cursor_foreground_priority)
            self.assertIsInstance(row[0], Text)
            self.assertEqual(
                f"{WARNING_INDICATOR} ff",
                row[0].plain,
            )
            self.assertEqual(WARNING_STYLE, row[0].style)
            self.assertEqual("paid", row[1])
            self.assertEqual("0.005 KB", row[2])

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
            self.assertEqual("0.00 KB", row[2])

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
