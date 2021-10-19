from unittest import TestCase

from kaskade.kafka.models import Cluster, Topic
from tests import faker


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


class TestTopic(TestCase):
    def test_str(self):
        random_name = faker.word()
        topic = Topic(name=random_name)

        self.assertEqual(random_name, str(topic))
