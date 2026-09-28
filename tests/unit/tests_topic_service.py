import asyncio
import unittest
from concurrent.futures import Future
from unittest.mock import MagicMock, patch

from confluent_kafka import (
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

from kaskade.commands import CreateTopicCommand
from kaskade.models import (
    MetricState,
    Topic,
)
from kaskade.timeouts import TimeoutConfig
from kaskade.topic_service import TopicService
from tests import completed, failed, faker


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


def group_description(group_id: str) -> ConsumerGroupDescription:
    return ConsumerGroupDescription(
        group_id=group_id,
        is_simple_consumer_group=True,
        partition_assignor="range",
        state=CONSUMER_GROUP_STATE_STABLE,
        members=[],
        coordinator=Node(1, "localhost", 9092),
    )


def group_authorization_error() -> KafkaException:
    return KafkaException(KafkaError(KafkaError.GROUP_AUTHORIZATION_FAILED))


def mock_groups(
    admin: MagicMock,
    descriptions: dict[str, Future[object]],
    offsets: dict[str, Future[object]],
) -> None:
    admin.list_consumer_groups.return_value = completed(
        ListConsumerGroupsResult(
            valid=[ConsumerGroupListing(group_id, True) for group_id in descriptions]
        )
    )
    admin.describe_consumer_groups.return_value = descriptions
    admin.list_consumer_group_offsets.side_effect = lambda request, **_: {
        request[0].group_id: offsets[request[0].group_id]
    }


class TestTopicService(unittest.IsolatedAsyncioTestCase):
    @patch("kaskade.topic_service.AdminClient")
    async def test_maps_create_command_at_kafka_boundary(self, mock_class_admin: MagicMock) -> None:
        admin = mock_class_admin.return_value
        admin.create_topics.return_value = {"orders": completed(None)}
        command = CreateTopicCommand("orders", 3, 2, 1, "compact", 1000)

        service = TopicService(
            {"bootstrap.servers": "localhost:9092"},
            timeouts=TimeoutConfig(admin_write=90),
        )
        service.create(command)

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
        self.assertEqual(10.0, service.timeouts.admin_read)
        self.assertEqual(90.0, service.timeouts.admin_write)
        admin.create_topics.assert_called_once_with(
            [new_topic], request_timeout=service.timeouts.admin_write
        )

    @patch("kaskade.topic_service.AdminClient")
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

    @patch("kaskade.topic_service.AdminClient")
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

    @patch("kaskade.topic_service.Consumer", create=True)
    @patch("kaskade.topic_service.AdminClient")
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

    @patch("kaskade.topic_service.Consumer", create=True)
    @patch("kaskade.topic_service.AdminClient")
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

    @patch("kaskade.topic_service.AdminClient")
    async def test_marks_failed_metrics_unavailable(self, mock_class_admin: MagicMock) -> None:
        topic_name = "orders"
        metadata = topic_metadata(topic_name, 0)
        admin = mock_class_admin.return_value
        admin.list_topics.return_value.topics = {topic_name: metadata}

        def list_offsets(request: dict[TopicPartition, object], **_: object) -> object:
            if admin.list_offsets.call_count == 1:
                return {partition: failed(KafkaException("unavailable")) for partition in request}
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

    @patch("kaskade.topic_service.AdminClient")
    async def test_propagates_programming_errors_from_offsets(
        self, mock_class_admin: MagicMock
    ) -> None:
        topic_name = "orders"
        admin = mock_class_admin.return_value
        admin.list_topics.return_value.topics = {topic_name: topic_metadata(topic_name, 0)}
        admin.list_offsets.side_effect = lambda request, **_: {
            partition: failed(TypeError("bad argument")) for partition in request
        }
        service = TopicService({"bootstrap.servers": "localhost:9092"})
        topics = await service.metadata()

        with self.assertRaisesRegex(TypeError, "bad argument"):
            await service.enrich_offsets(topics)

        self.assertIsNot(MetricState.UNAVAILABLE, topics[topic_name].records_state)

    @patch("kaskade.topic_service.AdminClient")
    async def test_propagates_programming_errors_from_groups(
        self, mock_class_admin: MagicMock
    ) -> None:
        admin = mock_class_admin.return_value
        admin.list_consumer_groups.return_value = failed(TypeError("bad argument"))
        service = TopicService({"bootstrap.servers": "localhost:9092"})

        with self.assertRaisesRegex(TypeError, "bad argument"):
            await service.load_groups()

    @patch("kaskade.topic_service.AdminClient")
    async def test_hides_unauthorized_groups_without_failing_refresh(
        self, mock_class_admin: MagicMock
    ) -> None:
        committed = TopicPartition("orders", 0, 30)
        # TopicPartition.error is read-only; the Kafka client sets it on offset results.
        unauthorized_partition = MagicMock(
            topic="orders", partition=0, error=KafkaError(KafkaError.GROUP_AUTHORIZATION_FAILED)
        )
        mock_groups(
            mock_class_admin.return_value,
            descriptions={
                "readable": completed(group_description("readable")),
                "hidden": failed(group_authorization_error()),
                "hidden-offsets": completed(group_description("hidden-offsets")),
                "hidden-partitions": completed(group_description("hidden-partitions")),
            },
            offsets={
                "readable": completed(ConsumerGroupTopicPartitions("readable", [committed])),
                "hidden": failed(group_authorization_error()),
                "hidden-offsets": failed(group_authorization_error()),
                "hidden-partitions": completed(
                    ConsumerGroupTopicPartitions("hidden-partitions", [unauthorized_partition])
                ),
            },
        )
        service = TopicService({"bootstrap.servers": "localhost:9092"})

        with self.assertLogs("kaskade", level="INFO") as logs:
            snapshot = await service.load_groups()

        self.assertEqual((), snapshot.errors)
        self.assertEqual(["readable"], [item.group_id for item in snapshot.descriptions])
        self.assertEqual({"readable": (committed,)}, snapshot.offsets)
        self.assertIn("INFO:kaskade:admin groups hidden (not authorized)=3", logs.output)
        self.assertFalse([line for line in logs.output if line.startswith("ERROR")])

    @patch("kaskade.topic_service.AdminClient")
    async def test_other_group_errors_still_fail_refresh(self, mock_class_admin: MagicMock) -> None:
        mock_groups(
            mock_class_admin.return_value,
            descriptions={
                "readable": completed(group_description("readable")),
                "hidden": failed(group_authorization_error()),
                "timed-out": failed(KafkaException(KafkaError(KafkaError._TIMED_OUT))),
                "no-coordinator": completed(group_description("no-coordinator")),
            },
            offsets={
                "readable": completed(ConsumerGroupTopicPartitions("readable", [])),
                "hidden": failed(group_authorization_error()),
                "timed-out": completed(ConsumerGroupTopicPartitions("timed-out", [])),
                "no-coordinator": failed(
                    KafkaException(KafkaError(KafkaError.COORDINATOR_NOT_AVAILABLE))
                ),
            },
        )
        service = TopicService({"bootstrap.servers": "localhost:9092"})
        topics = {"orders": Topic("orders", records_state=MetricState.READY)}

        with self.assertLogs("kaskade", level="ERROR") as logs:
            snapshot = await service.load_groups()

        self.assertEqual(2, len(snapshot.errors))
        self.assertEqual(2, len(logs.output))
        self.assertIn("description failed for timed-out", logs.output[0])
        self.assertIn("offsets failed for no-coordinator", logs.output[1])
        self.assertFalse(service.apply_groups(topics, snapshot).successful)
        self.assertEqual(MetricState.UNAVAILABLE, topics["orders"].groups_state)

    @patch("kaskade.topic_service.AdminClient")
    async def test_unauthorized_group_listing_still_fails_refresh(
        self, mock_class_admin: MagicMock
    ) -> None:
        admin = mock_class_admin.return_value
        admin.list_consumer_groups.return_value = failed(group_authorization_error())
        service = TopicService({"bootstrap.servers": "localhost:9092"})

        with self.assertLogs("kaskade", level="ERROR"):
            snapshot = await service.load_groups()

        self.assertEqual(1, len(snapshot.errors))
        admin.describe_consumer_groups.assert_not_called()

    @patch("kaskade.topic_service.AdminClient")
    async def test_bounds_group_offset_concurrency(self, mock_class_admin: MagicMock) -> None:
        admin = mock_class_admin.return_value
        group_ids = [f"group-{index}" for index in range(20)]
        admin.list_consumer_groups.return_value = completed(
            ListConsumerGroupsResult(
                valid=[ConsumerGroupListing(group_id, True) for group_id in group_ids]
            )
        )
        admin.describe_consumer_groups.return_value = {
            group_id: completed(group_description(group_id)) for group_id in group_ids
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
