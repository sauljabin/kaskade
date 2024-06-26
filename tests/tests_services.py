import unittest
from unittest.mock import patch, MagicMock

from confluent_kafka import Node
from confluent_kafka.admin import (
    TopicMetadata,
    PartitionMetadata,
    ConsumerGroupDescription,
    MemberAssignment,
    MemberDescription,
    ConsumerGroupListing,
)
from confluent_kafka.cimpl import CONSUMER_GROUP_STATE_STABLE, TopicPartition

from kaskade.services import TopicService
from tests import faker


class TestTopicService(unittest.IsolatedAsyncioTestCase):

    @patch("kaskade.services.Consumer")
    @patch("kaskade.services.AdminClient")
    async def test_get_topics_without_group(self, mock_class_admin, mock_class_consumer):
        # prepare get_watermark
        expected_low_watermark = 0
        expected_high_watermark = 50

        mock_consumer = MagicMock()
        mock_class_consumer.return_value = mock_consumer
        mock_consumer.get_watermark_offsets.return_value = (
            expected_low_watermark,
            expected_high_watermark,
        )

        # prepare topic: 1 topic and 1 partition
        expected_topic_name = faker.word()

        partition_metadata = PartitionMetadata()
        partition_metadata.id = faker.pyint()
        partition_metadata.isrs = [0, 1]
        partition_metadata.replicas = [0, 1, 2]

        topic_metadata = TopicMetadata()
        topic_metadata.topic = expected_topic_name
        topic_metadata.partitions = {partition_metadata.id: partition_metadata}

        # prepare list_topics
        mock_admin = MagicMock()
        mock_class_admin.return_value = mock_admin
        mock_admin.list_topics.return_value.topics = {topic_metadata.topic: topic_metadata}

        # prepare consumer groups: no groups
        mock_admin.list_consumer_groups.return_value.result.return_value.valid = []

        # asserts
        topic_service = TopicService({"bootstrap.servers": faker.hostname()})

        topics_list = await topic_service.all()
        self.assertEqual(1, len(topics_list))

        topic = topics_list[expected_topic_name]
        self.assertEqual(expected_topic_name, topic.name)

        partitions_list = topic.partitions
        self.assertEqual(1, len(partitions_list))

        partition = partitions_list[0]
        self.assertEqual(expected_low_watermark, partition.low)
        self.assertEqual(expected_high_watermark, partition.high)

        groups_list = topic.groups
        self.assertEqual(0, len(groups_list))

        self.assertEqual(0, topic.groups_count())
        self.assertEqual(1, topic.partitions_count())
        self.assertEqual(2, topic.isrs_count())
        self.assertEqual(50, topic.records_count())
        self.assertEqual(3, topic.replicas_count())
        self.assertEqual(0, topic.lag())

    @patch("kaskade.services.Consumer")
    @patch("kaskade.services.AdminClient")
    async def test_get_topics_with_group(self, mock_class_admin, mock_class_consumer):
        # prepare get_watermark
        expected_low_watermark = 0
        expected_high_watermark = 50

        mock_consumer = MagicMock()
        mock_class_consumer.return_value = mock_consumer
        mock_consumer.get_watermark_offsets.return_value = (
            expected_low_watermark,
            expected_high_watermark,
        )

        # prepare topic: 1 topic and 1 partition
        expected_topic_name = faker.word()

        partition_metadata = PartitionMetadata()
        partition_metadata.id = faker.pyint()
        partition_metadata.isrs = [0, 1]
        partition_metadata.replicas = [0, 1, 2]

        topic_metadata = TopicMetadata()
        topic_metadata.topic = expected_topic_name
        topic_metadata.partitions = {partition_metadata.id: partition_metadata}

        # prepare list_topics
        mock_admin = MagicMock()
        mock_class_admin.return_value = mock_admin
        mock_admin.list_topics.return_value.topics = {topic_metadata.topic: topic_metadata}

        # prepare consumer groups: no groups
        expected_group_name = faker.word()
        expected_partition_assignor = faker.word()
        expected_member_id = expected_group_name + "-1"
        expected_client_id = expected_group_name + "-client"
        expected_host = faker.hostname()
        expected_node_id = 1
        expected_node_port = 9092
        expected_offset = 30

        commited_partition_metadata = TopicPartition(
            expected_topic_name, partition_metadata.id, expected_offset
        )
        consume_group_assignment = MemberAssignment([commited_partition_metadata])
        consumer_group_member_metadata = MemberDescription(
            member_id=expected_member_id,
            client_id=expected_client_id,
            host=expected_host,
            assignment=consume_group_assignment,
        )
        consumer_group_node_metadata = Node(expected_node_id, expected_host, expected_node_port)
        consumer_group_metadata = ConsumerGroupDescription(
            group_id=expected_group_name,
            is_simple_consumer_group=True,
            partition_assignor=expected_partition_assignor,
            state=CONSUMER_GROUP_STATE_STABLE,
            members=[consumer_group_member_metadata],
            coordinator=consumer_group_node_metadata,
        )

        mock_describe_consumer_result = MagicMock()
        mock_describe_consumer_result.result.return_value = consumer_group_metadata
        mock_admin.list_consumer_groups.return_value.result.return_value.valid = [
            ConsumerGroupListing(expected_group_name, True)
        ]
        mock_admin.describe_consumer_groups.return_value.items.return_value = [
            (expected_group_name, mock_describe_consumer_result)
        ]
        mock_consumer.committed.return_value = [commited_partition_metadata]

        # asserts
        topic_service = TopicService({"bootstrap.servers": faker.hostname()})

        topics_list = await topic_service.all()
        self.assertEqual(1, len(topics_list))

        topic = topics_list[expected_topic_name]
        self.assertEqual(expected_topic_name, topic.name)

        partitions_list = topic.partitions
        self.assertEqual(1, len(partitions_list))

        partition = partitions_list[0]
        self.assertEqual(expected_low_watermark, partition.low)
        self.assertEqual(expected_high_watermark, partition.high)

        groups_list = topic.groups
        self.assertEqual(1, len(groups_list))

        group = groups_list[0]
        self.assertEqual(1, group.partitions_count())
        self.assertEqual(1, group.members_count())
        self.assertEqual(20, group.lag_count())

        member = group.members[0]
        self.assertEqual(expected_member_id, member.id)

        self.assertEqual(1, topic.groups_count())
        self.assertEqual(1, topic.partitions_count())
        self.assertEqual(2, topic.isrs_count())
        self.assertEqual(50, topic.records_count())
        self.assertEqual(3, topic.replicas_count())
        self.assertEqual(20, topic.lag())
