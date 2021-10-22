from unittest import TestCase

from kaskade.kafka.models import Cluster, Group, Partition, Topic
from tests import faker
from tests.kafka import random_broker, random_cluster, random_groups, random_partitions


class TestGroup(TestCase):
    def test_str(self):
        random_name = faker.word()
        group = Group(id=random_name)

        self.assertEqual(random_name, str(group))
        self.assertEqual(random_name, repr(group))


class TestPartition(TestCase):
    def test_str(self):
        random_id = faker.pyint()
        partition = Partition(id=random_id)

        self.assertEqual(str(random_id), str(partition))
        self.assertEqual(str(random_id), repr(partition))


class TestBroker(TestCase):
    def test_str(self):
        broker = random_broker()

        expected = broker.host + ":" + str(broker.port) + "/" + str(broker.id)
        self.assertEqual(expected, str(broker))
        self.assertEqual(expected, repr(broker))


class TestCluster(TestCase):
    def test_str(self):
        brokers = faker.pydict()
        version = faker.bothify("#.#.#")
        has_schemas = faker.pybool()
        protocol = faker.word()

        values = {
            "brokers": [str(broker) for broker in brokers],
            "version": version,
            "has_schemas": has_schemas,
            "protocol": protocol,
        }

        expected_str = str(values)

        cluster = Cluster(
            brokers=brokers, version=version, has_schemas=has_schemas, protocol=protocol
        )

        self.assertEqual(expected_str, str(cluster))
        self.assertEqual(expected_str, repr(cluster))

    def test_broker_count_zero_if_None(self):
        topic = random_cluster()

        topic.brokers = []
        self.assertEqual(0, topic.brokers_count())

        topic.brokers = None
        self.assertEqual(0, topic.brokers_count())


class TestTopic(TestCase):
    def test_str(self):
        random_name = faker.word()
        topic = Topic(name=random_name)

        self.assertEqual(random_name, str(topic))
        self.assertEqual(random_name, repr(topic))

    def test_partitions_count(self):
        partitions = random_partitions()
        topic = Topic(partitions=partitions)

        self.assertEqual(len(partitions), topic.partitions_count())

    def test_partitions_count_zero_if_partitions_are_None(self):
        topic = Topic()

        self.assertEqual(0, topic.partitions_count())
        self.assertEqual(0, topic.replicas_count())
        self.assertEqual(0, topic.isrs_count())

        topic.partitions = None
        self.assertEqual(0, topic.partitions_count())
        self.assertEqual(0, topic.replicas_count())
        self.assertEqual(0, topic.isrs_count())

    def test_groups_count(self):
        groups = random_groups()
        topic = Topic(groups=groups)

        self.assertEqual(len(groups), topic.groups_count())

    def test_groups_count_zero_if_groups_are_None(self):
        topic = Topic()

        self.assertEqual(0, topic.groups_count())

    def test_replicas_count(self):
        partitions = random_partitions()
        topic = Topic(partitions=partitions)
        max_val = max([len(partition.replicas) for partition in partitions])

        self.assertEqual(max_val, topic.replicas_count())

    def test_in_sync_replicas_count(self):
        partitions = random_partitions()
        topic = Topic(partitions=partitions)
        min_val = min([len(partition.isrs) for partition in partitions])

        self.assertEqual(min_val, topic.isrs_count())
