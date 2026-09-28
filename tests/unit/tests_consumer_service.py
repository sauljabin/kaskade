import asyncio
import threading
import unittest
from time import perf_counter
from unittest.mock import MagicMock, patch

from confluent_kafka import (
    OFFSET_BEGINNING,
    OFFSET_END,
    KafkaError,
    KafkaException,
)
from confluent_kafka.cimpl import TopicPartition

from kaskade.commands import RecordFilters
from kaskade.concurrency import run_blocking
from kaskade.configs import AUTO_OFFSET_RESET, EARLIEST, GROUP_ID
from kaskade.consumer_service import ConsumerService
from kaskade.deserializers import (
    Deserialization,
    Deserializer,
    DeserializerPool,
    StringDeserializer,
)
from kaskade.models import (
    Header,
    PartitionOffset,
    PartitionSelection,
    Record,
)
from kaskade.timeouts import TimeoutConfig


def consumer_message(
    *,
    partition: int = 0,
    key: bytes = b"key",
    value: bytes = b"value",
    headers: list[tuple[str, bytes]] | None = None,
    error: object | None = None,
) -> MagicMock:
    message = MagicMock()
    message.error.return_value = error
    message.timestamp.return_value = (0, 0)
    message.partition.return_value = partition
    message.offset.return_value = 1
    message.key.return_value = key
    message.value.return_value = value
    message.headers.return_value = headers or []
    return message


class TestConsumerService(unittest.IsolatedAsyncioTestCase):
    def test_null_filters_use_json_literal_instead_of_python_literal(self) -> None:
        record = Record(headers=[Header("nullable", None)])

        filters = (
            ("key", RecordFilters(key="null"), RecordFilters(key="None")),
            ("value", RecordFilters(value="null"), RecordFilters(value="None")),
            ("header", RecordFilters(header="null"), RecordFilters(header="None")),
        )
        for field, null_filter, none_filter in filters:
            with self.subTest(field=field):
                self.assertTrue(ConsumerService._matches(record, null_filter))
                self.assertFalse(ConsumerService._matches(record, none_filter))

    @patch("kaskade.consumer_service.Consumer")
    async def test_assigns_only_explicit_partitions_at_selected_offsets(
        self, mock_class_consumer: MagicMock
    ) -> None:
        consumer = mock_class_consumer.return_value
        topic = MagicMock(error=None, partitions={0: object(), 1: object(), 2: object()})
        consumer.list_topics.return_value.topics = {"orders": topic}
        consumer.get_watermark_offsets.return_value = (0, 100)
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
            partitions=(
                PartitionSelection(0),
                PartitionSelection(1, 0),
                PartitionSelection(2, PartitionOffset.EARLIEST),
            ),
            timeouts=TimeoutConfig(consumer_request=20),
        )
        consumer.list_topics.assert_not_called()
        consumer.get_watermark_offsets.assert_not_called()

        service.start()

        assignments = consumer.assign.call_args.args[0]
        self.assertEqual(
            [(0, OFFSET_END), (1, 0), (2, OFFSET_BEGINNING)],
            [(assignment.partition, assignment.offset) for assignment in assignments],
        )
        consumer.subscribe.assert_not_called()
        consumer.get_watermark_offsets.assert_called_once_with(
            TopicPartition("orders", 1),
            timeout=service.timeouts.consumer_request,
            cached=False,
        )
        consumer.list_topics.assert_called_once_with(
            "orders", timeout=service.timeouts.consumer_request
        )
        self.assertEqual(20.0, service.timeouts.consumer_request)
        self.assertTrue(service.stable)

        service.close()
        consumer.unassign.assert_called_once_with()
        consumer.unsubscribe.assert_not_called()

    @patch("kaskade.consumer_service.Consumer")
    async def test_earliest_assigns_every_partition_without_committed_offsets(
        self, mock_class_consumer: MagicMock
    ) -> None:
        consumer = mock_class_consumer.return_value
        topic = MagicMock(error=None, partitions={0: object(), 1: object(), 2: object()})
        consumer.list_topics.return_value.topics = {"orders": topic}

        service = ConsumerService(
            "orders",
            {
                "bootstrap.servers": "localhost:9092",
                AUTO_OFFSET_RESET: EARLIEST,
            },
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
        )
        consumer.list_topics.assert_not_called()

        service.start()

        assignments = consumer.assign.call_args.args[0]
        self.assertEqual(
            [(0, OFFSET_BEGINNING), (1, OFFSET_BEGINNING), (2, OFFSET_BEGINNING)],
            [(assignment.partition, assignment.offset) for assignment in assignments],
        )
        self.assertRegex(
            mock_class_consumer.call_args.args[0][GROUP_ID],
            r"^kaskade-[0-9a-f]{8}$",
        )
        self.assertEqual(
            mock_class_consumer.call_args.args[0][GROUP_ID],
            service.group_id,
        )
        consumer.list_topics.assert_called_once_with(
            "orders", timeout=service.timeouts.consumer_request
        )
        consumer.subscribe.assert_not_called()
        self.assertTrue(service.stable)

        service.close()
        consumer.unassign.assert_called_once_with()

    @patch("kaskade.consumer_service.Consumer")
    async def test_honors_configured_group_id(self, mock_class_consumer: MagicMock) -> None:
        consumer = mock_class_consumer.return_value
        service = ConsumerService(
            "orders",
            {
                "bootstrap.servers": "localhost:9092",
                GROUP_ID: "authorized-reader",
            },
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
        )

        self.assertEqual(
            "authorized-reader",
            mock_class_consumer.call_args.args[0][GROUP_ID],
        )
        self.assertEqual("authorized-reader", service.group_id)

        service.close()
        consumer.unsubscribe.assert_called_once_with()

    @patch("kaskade.consumer_service.Consumer")
    async def test_surfaces_group_authorization_callback(
        self, mock_class_consumer: MagicMock
    ) -> None:
        consumer = mock_class_consumer.return_value
        consumer.consume.return_value = []
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
        )
        error = KafkaError(
            KafkaError.GROUP_AUTHORIZATION_FAILED,
            "Group authorization failed",
        )
        error_callback = mock_class_consumer.call_args.args[0]["error_cb"]
        error_callback(error)

        with self.assertRaisesRegex(KafkaException, "Group authorization failed"):
            await service.consume()

    @patch("kaskade.consumer_service.Consumer")
    async def test_rejects_nonexistent_explicit_partition(
        self, mock_class_consumer: MagicMock
    ) -> None:
        consumer = mock_class_consumer.return_value
        topic = MagicMock(error=None, partitions={0: object()})
        consumer.list_topics.return_value.topics = {"orders": topic}

        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
            partitions=(PartitionSelection(2),),
        )

        with self.assertRaisesRegex(ValueError, "Partition 2 does not exist"):
            service.start()

        consumer.assign.assert_not_called()
        self.assertFalse(service.started)

    @patch("kaskade.consumer_service.Consumer")
    async def test_rejects_explicit_offset_outside_watermarks(
        self, mock_class_consumer: MagicMock
    ) -> None:
        consumer = mock_class_consumer.return_value
        topic = MagicMock(error=None, partitions={0: object()})
        consumer.list_topics.return_value.topics = {"orders": topic}
        consumer.get_watermark_offsets.return_value = (10, 20)

        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
            partitions=(PartitionSelection(0, 0),),
        )

        with self.assertRaisesRegex(ValueError, "Offset 0 is out of range"):
            service.start()

        consumer.assign.assert_not_called()

    @patch("kaskade.consumer_service.Consumer")
    async def test_consume_starts_the_consumer_once(self, mock_class_consumer: MagicMock) -> None:
        consumer = mock_class_consumer.return_value
        consumer.consume.return_value = []
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
            timeouts=TimeoutConfig(consumer_idle=0.1, consumer_poll=0.1, consumer_assignment=0.1),
        )
        consumer.subscribe.assert_not_called()

        await service.consume()
        await service.consume()

        consumer.subscribe.assert_called_once()
        self.assertTrue(service.started)

    @patch("kaskade.consumer_service.Consumer")
    async def test_close_releases_the_client_when_unsubscribe_fails(
        self, mock_class_consumer: MagicMock
    ) -> None:
        consumer = mock_class_consumer.return_value
        consumer.unsubscribe.side_effect = KafkaException("unsubscribe failed")
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
        )

        with self.assertRaisesRegex(KafkaException, "unsubscribe failed"):
            service.close()

        consumer.close.assert_called_once_with()

    @patch("kaskade.consumer_service.Consumer")
    async def test_consumes_records_in_batches(self, mock_class_consumer: MagicMock) -> None:
        message = MagicMock()
        message.error.return_value = None
        message.timestamp.return_value = (1, 1000)
        message.partition.return_value = 0
        message.offset.return_value = 1
        message.key.return_value = b"key"
        message.value.return_value = b"value"
        message.headers.return_value = []
        consumer = mock_class_consumer.return_value
        consumer.consume.return_value = [message]
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
            page_size=1,
        )
        service.on_assign(consumer, [TopicPartition("orders", 0)])

        records = await service.consume()

        self.assertEqual(1, len(records))
        self.assertEqual("key", records[0].key_str())
        self.assertEqual("1970-01-01T00:00:01.000Z", records[0].dict()["timestamp"])
        consumer.consume.assert_called_once_with(1, timeout=service.timeouts.consumer_poll)

    @patch("kaskade.consumer_service.Consumer")
    async def test_blocking_deserialization_does_not_block_event_loop(
        self, mock_class_consumer: MagicMock
    ) -> None:
        started = threading.Event()
        release = threading.Event()
        deserialization_started_at: list[float] = []
        event_loop_observed_at: list[float] = []

        class BlockingDeserializer(Deserializer):
            def deserialize(self, data, topic=None, context=None):
                deserialization_started_at.append(perf_counter())
                started.set()
                release.wait(timeout=1)
                return data.decode()

        async def observe_started() -> None:
            await asyncio.to_thread(started.wait, 1)
            event_loop_observed_at.append(perf_counter())
            release.set()

        consumer = mock_class_consumer.return_value
        consumer.consume.return_value = [consumer_message()]
        deserializer_factory = MagicMock(spec=DeserializerPool)
        deserializer_factory.get.side_effect = [
            StringDeserializer(),
            BlockingDeserializer(),
            StringDeserializer(),
        ]
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            deserializer_factory,
            Deserialization.STRING,
            Deserialization.STRING,
            page_size=1,
        )
        service.on_assign(consumer, [TopicPartition("orders", 0)])
        release_timer = threading.Timer(0.5, release.set)
        self.addCleanup(release_timer.cancel)
        release_timer.start()

        records, _ = await asyncio.gather(service.consume(), observe_started())

        self.assertEqual("value", records[0].value_str())
        self.assertLess(
            event_loop_observed_at[0] - deserialization_started_at[0],
            0.2,
        )

    @patch("kaskade.consumer_service.Consumer")
    async def test_deserialization_fallback_is_per_field_and_per_record(
        self, mock_class_consumer: MagicMock
    ) -> None:
        consumer = mock_class_consumer.return_value
        consumer.consume.return_value = [
            consumer_message(key=b"valid-1", value=b"value-1"),
            consumer_message(key=b"\xff", value=b"value-2"),
            consumer_message(key=b"valid-3", value=b"value-3"),
        ]
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
            page_size=3,
        )
        service.on_assign(consumer, [TopicPartition("orders", 0)])

        records = await service.consume()

        self.assertEqual(["valid-1", "/w==", "valid-3"], [r.key_str() for r in records])
        self.assertEqual(["value-1", "value-2", "value-3"], [r.value_str() for r in records])
        self.assertFalse(records[0].has_deserialization_errors())
        self.assertTrue(records[1].key_outcome().used_fallback)
        self.assertFalse(records[1].value_outcome().used_fallback)
        self.assertFalse(records[2].has_deserialization_errors())
        self.assertEqual(
            {
                "message": "'utf-8' codec can't decode byte 0xff in position 0: invalid start byte",
                "fallback": "BYTES",
                "encoding": "BASE64",
            },
            records[1].dict()["key"]["error"],
        )

    @patch("kaskade.consumer_service.Consumer")
    async def test_byte_and_fallback_encodings_are_independent(
        self, mock_class_consumer: MagicMock
    ) -> None:
        consumer = mock_class_consumer.return_value
        consumer.consume.return_value = [
            consumer_message(
                key=b"Hello world",
                value=b"Hello world",
                headers=[("binary", b"\xff")],
            )
        ]
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            DeserializerPool(),
            Deserialization.BYTES,
            Deserialization.BYTES,
            bytes_config={
                "encoding": "base64",
                "key.encoding": "hex",
                "value.encoding": "byte-array",
            },
            fallback_config={"encoding": "escaped"},
        )
        service.on_assign(consumer, [TopicPartition("orders", 0)])

        record = (await service.consume())[0]

        self.assertEqual(
            "48656c6c6f20776f726c64",
            record.dict()["key"]["content"],
        )
        self.assertEqual(
            "BYTES",
            record.dict()["key"]["deserializer"],
        )
        self.assertEqual("HEX", record.dict()["key"]["encoding"])
        self.assertEqual(
            [72, 101, 108, 108, 111, 32, 119, 111, 114, 108, 100],
            record.dict()["value"]["content"],
        )
        self.assertEqual(
            "BYTES",
            record.dict()["value"]["deserializer"],
        )
        self.assertEqual("BYTE_ARRAY", record.dict()["value"]["encoding"])
        self.assertEqual(
            {
                "key": "binary",
                "value": "\\xff",
                "error": {
                    "message": (
                        "'utf-8' codec can't decode byte 0xff in position 0: " "invalid start byte"
                    ),
                    "fallback": "BYTES",
                    "encoding": "ESCAPED",
                },
            },
            record.dict()["headers"][0],
        )

    @patch("kaskade.consumer_service.Consumer")
    async def test_fallback_encoding_is_global_for_deserialization_errors(
        self, mock_class_consumer: MagicMock
    ) -> None:
        consumer = mock_class_consumer.return_value
        consumer.consume.return_value = [
            consumer_message(
                key=b"\xff",
                value=b"\xfe",
                headers=[("binary", b"\xfd")],
            )
        ]
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
            fallback_config={"encoding": "escaped"},
            page_size=1,
        )
        service.on_assign(consumer, [TopicPartition("orders", 0)])

        with self.assertLogs("kaskade", level="WARNING") as logs:
            record = (await service.consume())[0]

        data = record.dict()
        self.assertEqual("\\xff", data["key"]["content"])
        self.assertEqual(
            ("BYTES", "ESCAPED"),
            (data["key"]["error"]["fallback"], data["key"]["error"]["encoding"]),
        )
        self.assertEqual("\\xfe", data["value"]["content"])
        self.assertEqual(
            ("BYTES", "ESCAPED"),
            (
                data["value"]["error"]["fallback"],
                data["value"]["error"]["encoding"],
            ),
        )
        self.assertEqual("\\xfd", data["headers"][0]["value"])
        self.assertEqual(
            ("BYTES", "ESCAPED"),
            (
                data["headers"][0]["error"]["fallback"],
                data["headers"][0]["error"]["encoding"],
            ),
        )
        self.assertEqual(
            2,
            sum("fallback=BYTES encoding=ESCAPED" in log for log in logs.output),
        )

    @patch("kaskade.consumer_service.Consumer")
    async def test_filters_batches_until_a_record_matches(
        self, mock_class_consumer: MagicMock
    ) -> None:
        consumer = mock_class_consumer.return_value
        consumer.consume.side_effect = [
            [consumer_message(partition=0)],
            [
                consumer_message(
                    partition=1,
                    key=b"customer-1",
                    value=b"paid",
                    headers=[("source", b"checkout")],
                )
            ],
        ]
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
            page_size=1,
        )
        service.on_assign(consumer, [TopicPartition("orders", 1)])

        records = await service.consume(
            filters=RecordFilters(
                partition=1,
                key="customer",
                value="paid",
                header="checkout",
            )
        )

        self.assertEqual(1, len(records))
        self.assertEqual(2, consumer.consume.call_count)

    @patch("kaskade.consumer_service.Consumer")
    async def test_stops_after_empty_batch_retries(self, mock_class_consumer: MagicMock) -> None:
        consumer = mock_class_consumer.return_value
        consumer.consume.return_value = []
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
            timeouts=TimeoutConfig(consumer_idle=1),
        )
        service.on_assign(consumer, [TopicPartition("orders", 0)])

        self.assertEqual([], await service.consume())
        self.assertEqual(2, consumer.consume.call_count)

    @patch("kaskade.consumer_service.Consumer")
    async def test_raises_kafka_message_errors(self, mock_class_consumer: MagicMock) -> None:
        error = MagicMock()
        consumer = mock_class_consumer.return_value
        consumer.consume.return_value = [consumer_message(error=error)]
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
            page_size=1,
        )
        service.on_assign(consumer, [TopicPartition("orders", 0)])

        with self.assertRaises(KafkaException):
            await service.consume()

    @patch("kaskade.consumer_service.Consumer")
    async def test_reuses_deserializer_instances_and_closes(
        self, mock_class_consumer: MagicMock
    ) -> None:
        consumer = mock_class_consumer.return_value
        consumer.consume.return_value = [consumer_message()]
        deserializer_factory = MagicMock(spec=DeserializerPool)
        deserializer_factory.get.return_value = StringDeserializer()
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            deserializer_factory,
            Deserialization.STRING,
            Deserialization.STRING,
            page_size=1,
        )
        service.on_assign(consumer, [TopicPartition("orders", 0)])

        await service.consume()
        service.close()

        self.assertEqual(3, deserializer_factory.get.call_count)
        consumer.unsubscribe.assert_called_once_with()
        consumer.close.assert_called_once_with()

    @patch("kaskade.consumer_service.Consumer")
    async def test_deserializes_each_polled_batch_in_one_worker_call(
        self, mock_class_consumer: MagicMock
    ) -> None:
        consumer = mock_class_consumer.return_value
        consumer.consume.return_value = [
            consumer_message(key=f"key-{number}".encode()) for number in range(3)
        ]
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
            page_size=3,
        )
        service.on_assign(consumer, [TopicPartition("orders", 0)])

        with patch("kaskade.consumer_service.run_blocking", wraps=run_blocking) as worker_call:
            records = await service.consume()

        self.assertEqual(["key-0", "key-1", "key-2"], [record.key_str() for record in records])
        self.assertEqual(
            [service.start, consumer.consume, service._records_from_batch],
            [call.args[0] for call in worker_call.call_args_list],
        )

    @patch("kaskade.consumer_service.Consumer")
    async def test_filters_and_limits_records_within_a_batch(
        self, mock_class_consumer: MagicMock
    ) -> None:
        consumer = mock_class_consumer.return_value
        consumer.consume.return_value = [
            consumer_message(key=key)
            for key in (b"match-1", b"other", b"match-2", b"match-3", b"match-4")
        ]
        deserialized_keys: list[bytes] = []

        class RecordingDeserializer(StringDeserializer):
            def deserialize(self, data, topic=None, context=None):
                deserialized_keys.append(data)
                return super().deserialize(data, topic, context)

        deserializer_factory = MagicMock(spec=DeserializerPool)
        deserializer_factory.get.side_effect = [
            RecordingDeserializer(),
            StringDeserializer(),
            StringDeserializer(),
        ]
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            deserializer_factory,
            Deserialization.STRING,
            Deserialization.STRING,
            page_size=3,
        )
        service.on_assign(consumer, [TopicPartition("orders", 0)])

        records = await service.consume(filters=RecordFilters(key="match"))

        self.assertEqual(
            ["match-1", "match-2", "match-3"], [record.key_str() for record in records]
        )
        self.assertEqual([b"match-1", b"other", b"match-2", b"match-3"], deserialized_keys)

    @patch("kaskade.consumer_service.Consumer")
    async def test_cancelling_consume_waits_for_the_batch_before_closing(
        self, mock_class_consumer: MagicMock
    ) -> None:
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        class BlockingDeserializer(Deserializer):
            def deserialize(self, data, topic=None, context=None):
                started.set()
                release.wait(timeout=2)
                finished.set()
                return data.decode()

        consumer = mock_class_consumer.return_value
        consumer.consume.return_value = [consumer_message(), consumer_message()]
        deserializer_factory = MagicMock(spec=DeserializerPool)
        deserializer_factory.get.side_effect = [
            StringDeserializer(),
            BlockingDeserializer(),
            StringDeserializer(),
        ]
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            deserializer_factory,
            Deserialization.STRING,
            Deserialization.STRING,
            page_size=2,
        )
        service.on_assign(consumer, [TopicPartition("orders", 0)])
        consume_task = asyncio.create_task(service.consume())
        await asyncio.to_thread(started.wait, 2)

        consume_task.cancel()
        close_task = asyncio.create_task(service.aclose())
        await asyncio.sleep(0.05)
        self.assertFalse(consume_task.done())
        consumer.close.assert_not_called()

        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await consume_task
        self.assertTrue(finished.is_set())
        await close_task
        consumer.close.assert_called_once_with()

    @patch("kaskade.consumer_service.Consumer")
    async def test_close_waits_for_active_consume(self, mock_class_consumer: MagicMock) -> None:
        entered_consume = threading.Event()
        release_consume = threading.Event()

        def blocking_consume(*_: object, **__: object) -> list[MagicMock]:
            entered_consume.set()
            release_consume.wait(timeout=2)
            return [consumer_message()]

        consumer = mock_class_consumer.return_value
        consumer.consume.side_effect = blocking_consume
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
            page_size=1,
        )
        service.on_assign(consumer, [TopicPartition("orders", 0)])
        consume_task = asyncio.create_task(service.consume())
        await asyncio.to_thread(entered_consume.wait, 2)

        close_task = asyncio.create_task(service.aclose())
        await asyncio.sleep(0)
        consumer.close.assert_not_called()

        release_consume.set()
        await consume_task
        await close_task
        consumer.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
