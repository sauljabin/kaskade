import asyncio
import threading
import unittest
from concurrent.futures import Future
from time import perf_counter
from unittest.mock import MagicMock, patch

from confluent_kafka import (
    OFFSET_BEGINNING,
    OFFSET_END,
    ConsumerGroupTopicPartitions,
    KafkaError,
    KafkaException,
    Node,
)
from confluent_kafka.admin import (
    ConfigEntry,
    ConsumerGroupDescription,
    ConsumerGroupListing,
    ListConsumerGroupsResult,
    ListOffsetsResultInfo,
    MemberAssignment,
    MemberDescription,
    PartitionMetadata,
    TopicMetadata,
)
from confluent_kafka.cimpl import CONSUMER_GROUP_STATE_STABLE, TopicPartition

from kaskade.commands import CreateTopicCommand, RecordFilters
from kaskade.configs import AUTO_OFFSET_RESET, EARLIEST, GROUP_ID
from kaskade.deserializers import (
    Deserialization,
    Deserializer,
    DeserializerPool,
    StringDeserializer,
)
from kaskade.models import Header, MetricState, PartitionOffset, PartitionSelection, Record
from kaskade.services import ConsumerService, TopicService
from tests import faker


def completed(value: object) -> Future[object]:
    future: Future[object] = Future()
    future.set_result(value)
    return future


def failed(error: Exception) -> Future[object]:
    future: Future[object] = Future()
    future.set_exception(error)
    return future


async def load_topics(service: TopicService) -> dict[str, object]:
    topics = await service.metadata()
    _, groups_snapshot = await asyncio.gather(
        service.enrich_offsets(topics),
        service.load_groups(),
    )
    service.apply_groups(topics, groups_snapshot)
    return topics


def topic_metadata(name: str, partition_id: int, partition_count: int = 1) -> TopicMetadata:
    topic = TopicMetadata()
    topic.topic = name
    topic.partitions = {}
    for current_partition_id in range(partition_id, partition_id + partition_count):
        partition = PartitionMetadata()
        partition.id = current_partition_id
        partition.leader = 0
        partition.isrs = [0, 1]
        partition.replicas = [0, 1, 2]
        topic.partitions[current_partition_id] = partition
    return topic


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


class TestTopicService(unittest.IsolatedAsyncioTestCase):
    @patch("kaskade.services.AdminClient")
    async def test_maps_create_command_at_kafka_boundary(self, mock_class_admin: MagicMock) -> None:
        admin = mock_class_admin.return_value
        admin.create_topics.return_value = {"orders": completed(None)}
        command = CreateTopicCommand("orders", 3, 2, 1, "compact", 1000)

        TopicService({"bootstrap.servers": "localhost:9092"}).create(command)

        new_topic = admin.create_topics.call_args.args[0][0]
        self.assertEqual("orders", new_topic.topic)
        self.assertEqual(3, new_topic.num_partitions)
        self.assertEqual(2, new_topic.replication_factor)
        self.assertEqual(
            {
                "cleanup.policy": "compact",
                "retention.ms": "1000",
                "min.insync.replicas": "1",
            },
            new_topic.config,
        )

    @patch("kaskade.services.AdminClient")
    async def test_create_topic_uses_broker_replication_defaults(
        self, mock_class_admin: MagicMock
    ) -> None:
        admin = mock_class_admin.return_value
        admin.create_topics.return_value = {"orders": completed(None)}
        command = CreateTopicCommand("orders", 3, None, None, "delete", 1000)

        TopicService({"bootstrap.servers": "localhost:9092"}).create(command)

        new_topic = admin.create_topics.call_args.args[0][0]
        self.assertEqual(-1, new_topic.replication_factor)
        self.assertEqual({"cleanup.policy": "delete", "retention.ms": "1000"}, new_topic.config)

    @patch("kaskade.services.AdminClient")
    async def test_describes_effective_topic_configurations(
        self, mock_class_admin: MagicMock
    ) -> None:
        admin = mock_class_admin.return_value
        entries = {
            "visible.setting": ConfigEntry(
                "visible.setting",
                "visible",
            ),
        }
        admin.describe_configs.return_value = {"orders": completed(entries)}

        configurations = TopicService({"bootstrap.servers": "localhost:9092"}).describe_configs(
            "orders"
        )

        self.assertEqual(
            {
                "visible.setting": "visible",
            },
            {configuration.name: configuration.value for configuration in configurations},
        )

    @patch("kaskade.services.Consumer")
    @patch("kaskade.services.AdminClient")
    async def test_batches_offsets_without_admin_consumers(
        self, mock_class_admin: MagicMock, mock_class_consumer: MagicMock
    ) -> None:
        topic_name = faker.word()
        partition_id = faker.pyint()
        metadata = topic_metadata(topic_name, partition_id, partition_count=25)
        admin = mock_class_admin.return_value
        admin.list_topics.return_value.topics = {topic_name: metadata}

        def list_offsets(request: dict[TopicPartition, object], **_: object) -> object:
            offset = 0 if admin.list_offsets.call_count == 1 else 50
            return {
                partition: completed(ListOffsetsResultInfo(offset, -1, -1)) for partition in request
            }

        admin.list_offsets.side_effect = list_offsets
        admin.list_consumer_groups.return_value = completed(ListConsumerGroupsResult(valid=[]))

        topics = await load_topics(TopicService({"bootstrap.servers": faker.hostname()}))

        topic = topics[topic_name]
        self.assertEqual(MetricState.READY, topic.records_state)
        self.assertEqual(MetricState.READY, topic.groups_state)
        self.assertEqual(1250, topic.records_count())
        self.assertEqual(2, admin.list_offsets.call_count)
        mock_class_consumer.assert_not_called()

    @patch("kaskade.services.Consumer")
    @patch("kaskade.services.AdminClient")
    async def test_maps_groups_with_one_offset_request_per_group(
        self, mock_class_admin: MagicMock, mock_class_consumer: MagicMock
    ) -> None:
        topic_name = faker.word()
        partition_id = faker.pyint()
        metadata = topic_metadata(topic_name, partition_id)
        admin = mock_class_admin.return_value
        admin.list_topics.return_value.topics = {topic_name: metadata}

        def list_offsets(request: dict[TopicPartition, object], **_: object) -> object:
            offset = 0 if admin.list_offsets.call_count == 1 else 50
            return {
                partition: completed(ListOffsetsResultInfo(offset, -1, -1)) for partition in request
            }

        admin.list_offsets.side_effect = list_offsets
        group_id = faker.word()
        committed = TopicPartition(topic_name, partition_id, 30)
        member = MemberDescription(
            member_id=f"{group_id}-1",
            client_id=f"{group_id}-client",
            host=faker.hostname(),
            assignment=MemberAssignment([committed]),
        )
        description = ConsumerGroupDescription(
            group_id=group_id,
            is_simple_consumer_group=True,
            partition_assignor="range",
            state=CONSUMER_GROUP_STATE_STABLE,
            members=[member],
            coordinator=Node(1, faker.hostname(), 9092),
        )
        admin.list_consumer_groups.return_value = completed(
            ListConsumerGroupsResult(valid=[ConsumerGroupListing(group_id, True)])
        )
        admin.describe_consumer_groups.return_value = {group_id: completed(description)}
        admin.list_consumer_group_offsets.return_value = {
            group_id: completed(ConsumerGroupTopicPartitions(group_id, [committed]))
        }

        topics = await load_topics(TopicService({"bootstrap.servers": faker.hostname()}))

        topic = topics[topic_name]
        self.assertEqual(1, topic.groups_count())
        self.assertEqual(1, topic.group_members_count())
        self.assertEqual(20, topic.lag())
        self.assertEqual(1, admin.list_consumer_group_offsets.call_count)
        mock_class_consumer.assert_not_called()

    @patch("kaskade.services.AdminClient")
    async def test_marks_failed_metrics_unavailable(self, mock_class_admin: MagicMock) -> None:
        topic_name = "orders"
        metadata = topic_metadata(topic_name, 0)
        admin = mock_class_admin.return_value
        admin.list_topics.return_value.topics = {topic_name: metadata}

        def list_offsets(request: dict[TopicPartition, object], **_: object) -> object:
            if admin.list_offsets.call_count == 1:
                return {partition: failed(RuntimeError("unavailable")) for partition in request}
            return {
                partition: completed(ListOffsetsResultInfo(50, -1, -1)) for partition in request
            }

        admin.list_offsets.side_effect = list_offsets
        admin.list_consumer_groups.return_value = completed(ListConsumerGroupsResult(valid=[]))

        topic = (await load_topics(TopicService({"bootstrap.servers": "localhost:9092"})))[
            topic_name
        ]

        self.assertEqual(MetricState.UNAVAILABLE, topic.records_state)
        self.assertEqual(MetricState.UNAVAILABLE, topic.groups_state)

    @patch("kaskade.services.AdminClient")
    async def test_bounds_group_offset_concurrency(self, mock_class_admin: MagicMock) -> None:
        admin = mock_class_admin.return_value
        group_ids = [f"group-{index}" for index in range(20)]
        admin.list_consumer_groups.return_value = completed(
            ListConsumerGroupsResult(
                valid=[ConsumerGroupListing(group_id, True) for group_id in group_ids]
            )
        )
        admin.describe_consumer_groups.return_value = {
            group_id: completed(
                ConsumerGroupDescription(
                    group_id=group_id,
                    is_simple_consumer_group=True,
                    partition_assignor="range",
                    state=CONSUMER_GROUP_STATE_STABLE,
                    members=[],
                    coordinator=Node(1, "localhost", 9092),
                )
            )
            for group_id in group_ids
        }
        pending: dict[str, Future[object]] = {}

        def list_group_offsets(request: list[ConsumerGroupTopicPartitions], **_: object) -> object:
            group_id = request[0].group_id
            future: Future[object] = Future()
            pending[group_id] = future
            return {group_id: future}

        admin.list_consumer_group_offsets.side_effect = list_group_offsets
        service = TopicService({"bootstrap.servers": "localhost:9092"})
        task = asyncio.create_task(service.load_groups())
        for _ in range(100):
            if len(pending) == service.GROUP_OFFSET_CONCURRENCY:
                break
            await asyncio.sleep(0)

        self.assertEqual(service.GROUP_OFFSET_CONCURRENCY, len(pending))
        while not task.done():
            for group_id, future in list(pending.items()):
                if not future.done():
                    future.set_result(ConsumerGroupTopicPartitions(group_id, []))
            await asyncio.sleep(0)
        await task
        self.assertEqual(len(group_ids), admin.list_consumer_group_offsets.call_count)


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

    @patch("kaskade.services.Consumer")
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
        )

        assignments = consumer.assign.call_args.args[0]
        self.assertEqual(
            [(0, OFFSET_END), (1, 0), (2, OFFSET_BEGINNING)],
            [(assignment.partition, assignment.offset) for assignment in assignments],
        )
        consumer.subscribe.assert_not_called()
        consumer.get_watermark_offsets.assert_called_once()
        self.assertTrue(service.stable)

        service.close()
        consumer.unassign.assert_called_once_with()
        consumer.unsubscribe.assert_not_called()

    @patch("kaskade.services.Consumer")
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

        assignments = consumer.assign.call_args.args[0]
        self.assertEqual(
            [(0, OFFSET_BEGINNING), (1, OFFSET_BEGINNING), (2, OFFSET_BEGINNING)],
            [(assignment.partition, assignment.offset) for assignment in assignments],
        )
        self.assertRegex(
            mock_class_consumer.call_args.args[0][GROUP_ID],
            r"^kaskade-[0-9a-f-]+$",
        )
        consumer.subscribe.assert_not_called()
        self.assertTrue(service.stable)

        service.close()
        consumer.unassign.assert_called_once_with()

    @patch("kaskade.services.Consumer")
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

        service.close()
        consumer.unsubscribe.assert_called_once_with()

    @patch("kaskade.services.Consumer")
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

    @patch("kaskade.services.Consumer")
    async def test_rejects_nonexistent_explicit_partition(
        self, mock_class_consumer: MagicMock
    ) -> None:
        consumer = mock_class_consumer.return_value
        topic = MagicMock(error=None, partitions={0: object()})
        consumer.list_topics.return_value.topics = {"orders": topic}

        with self.assertRaisesRegex(ValueError, "Partition 2 does not exist"):
            ConsumerService(
                "orders",
                {"bootstrap.servers": "localhost:9092"},
                DeserializerPool(),
                Deserialization.STRING,
                Deserialization.STRING,
                partitions=(PartitionSelection(2),),
            )

        consumer.assign.assert_not_called()
        consumer.close.assert_called_once_with()

    @patch("kaskade.services.Consumer")
    async def test_rejects_explicit_offset_outside_watermarks(
        self, mock_class_consumer: MagicMock
    ) -> None:
        consumer = mock_class_consumer.return_value
        topic = MagicMock(error=None, partitions={0: object()})
        consumer.list_topics.return_value.topics = {"orders": topic}
        consumer.get_watermark_offsets.return_value = (10, 20)

        with self.assertRaisesRegex(ValueError, "Offset 0 is out of range"):
            ConsumerService(
                "orders",
                {"bootstrap.servers": "localhost:9092"},
                DeserializerPool(),
                Deserialization.STRING,
                Deserialization.STRING,
                partitions=(PartitionSelection(0, 0),),
            )

        consumer.assign.assert_not_called()

    @patch("kaskade.services.Consumer")
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
        consumer.consume.assert_called_once_with(1, timeout=service.timeout)

    @patch("kaskade.services.Consumer")
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

    @patch("kaskade.services.Consumer")
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
            {"type": "BYTES", "encoding": "BASE64"},
            records[1].dict()["key"]["error"]["fallback"],
        )

    @patch("kaskade.services.Consumer")
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
            {"type": "BYTES", "encoding": "HEX"},
            record.dict()["key"]["deserializer"],
        )
        self.assertEqual(
            [72, 101, 108, 108, 111, 32, 119, 111, 114, 108, 100],
            record.dict()["value"]["content"],
        )
        self.assertEqual(
            {"type": "BYTES", "encoding": "BYTE_ARRAY"},
            record.dict()["value"]["deserializer"],
        )
        self.assertEqual(
            {
                "key": "binary",
                "value": "\\xff",
                "error": {
                    "message": (
                        "'utf-8' codec can't decode byte 0xff in position 0: " "invalid start byte"
                    ),
                    "fallback": {"type": "BYTES", "encoding": "ESCAPED"},
                },
            },
            record.dict()["headers"][0],
        )

    @patch("kaskade.services.Consumer")
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
            {"type": "BYTES", "encoding": "ESCAPED"},
            data["key"]["error"]["fallback"],
        )
        self.assertEqual("\\xfe", data["value"]["content"])
        self.assertEqual(
            {"type": "BYTES", "encoding": "ESCAPED"},
            data["value"]["error"]["fallback"],
        )
        self.assertEqual("\\xfd", data["headers"][0]["value"])
        self.assertEqual(
            {"type": "BYTES", "encoding": "ESCAPED"},
            data["headers"][0]["error"]["fallback"],
        )
        self.assertEqual(
            2,
            sum("fallback=BYTES encoding=ESCAPED" in log for log in logs.output),
        )

    @patch("kaskade.services.Consumer")
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

    @patch("kaskade.services.Consumer")
    async def test_stops_after_empty_batch_retries(self, mock_class_consumer: MagicMock) -> None:
        consumer = mock_class_consumer.return_value
        consumer.consume.return_value = []
        service = ConsumerService(
            "orders",
            {"bootstrap.servers": "localhost:9092"},
            DeserializerPool(),
            Deserialization.STRING,
            Deserialization.STRING,
            poll_retries=2,
        )
        service.on_assign(consumer, [TopicPartition("orders", 0)])

        self.assertEqual([], await service.consume())
        self.assertEqual(2, consumer.consume.call_count)

    @patch("kaskade.services.Consumer")
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

    @patch("kaskade.services.Consumer")
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

    @patch("kaskade.services.Consumer")
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
