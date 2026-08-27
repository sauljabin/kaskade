import asyncio
import unittest
from concurrent.futures import Future
from unittest.mock import MagicMock, patch

from confluent_kafka import ConsumerGroupTopicPartitions, Node
from confluent_kafka.admin import (
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

from kaskade.deserializers import Deserialization, DeserializerPool
from kaskade.models import MetricState
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


class TestTopicService(unittest.IsolatedAsyncioTestCase):
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

        topics = await TopicService({"bootstrap.servers": faker.hostname()}).all()

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

        topics = await TopicService({"bootstrap.servers": faker.hostname()}).all()

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

        topic = (await TopicService({"bootstrap.servers": "localhost:9092"}).all())[topic_name]

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
    @patch("kaskade.services.Consumer")
    async def test_consumes_records_in_batches(self, mock_class_consumer: MagicMock) -> None:
        message = MagicMock()
        message.error.return_value = None
        message.timestamp.return_value = (0, 0)
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
        consumer.consume.assert_called_once_with(1, timeout=service.timeout)


if __name__ == "__main__":
    unittest.main()
