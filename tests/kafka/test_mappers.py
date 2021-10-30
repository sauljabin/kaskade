from unittest import TestCase

from kaskade.kafka.mappers import (
    metadata_to_broker,
    metadata_to_group,
    metadata_to_group_partition,
    metadata_to_partition,
    metadata_to_topic,
)
from tests.kafka import (
    random_broker_metadata,
    random_group_metadata,
    random_partition_metadata,
    random_topic_metadata,
    random_topic_partition_metadata,
)


class TestMappers(TestCase):
    def test_metadata_to_broker(self):
        metadata = random_broker_metadata()

        actual = metadata_to_broker(metadata)

        self.assertEqual(metadata.id, actual.id)
        self.assertEqual(metadata.port, actual.port)
        self.assertEqual(metadata.host, actual.host)

    def test_metadata_to_group(self):
        metadata = random_group_metadata()
        metadata_broker = metadata.broker

        actual = metadata_to_group(metadata)
        actual_broker = actual.broker

        self.assertEqual(metadata.id, actual.id)
        self.assertEqual(metadata.state, actual.state)
        self.assertListEqual([], actual.partitions)
        self.assertEqual(len(metadata.members), actual.members)

        self.assertEqual(metadata_broker.id, actual_broker.id)
        self.assertEqual(metadata_broker.port, actual_broker.port)
        self.assertEqual(metadata_broker.host, actual_broker.host)

    def test_metadata_to_partition(self):
        metadata = random_partition_metadata()

        actual = metadata_to_partition(metadata)

        self.assertEqual(metadata.id, actual.id)
        self.assertEqual(metadata.isrs, actual.isrs)
        self.assertEqual(metadata.leader, actual.leader)
        self.assertEqual(metadata.replicas, actual.replicas)

    def test_metadata_to_group_partition(self):
        metadata = random_topic_partition_metadata()

        actual = metadata_to_group_partition(metadata)

        self.assertEqual(metadata.partition, actual.id)
        self.assertEqual(metadata.topic, actual.topic)
        self.assertEqual(metadata.offset, actual.offset)
        self.assertEqual("", actual.group)
        self.assertEqual(0, actual.high)
        self.assertEqual(0, actual.low)

    def test_metadata_to_topic(self):
        metadata = random_topic_metadata()

        actual = metadata_to_topic(metadata)

        self.assertEqual(metadata.topic, actual.name)
        self.assertListEqual([], actual.groups)
        self.assertListEqual([], actual.partitions)
