from unittest import TestCase
from unittest.mock import MagicMock, patch

import confluent_kafka
from confluent_kafka.admin import BrokerMetadata, ConfigEntry

from kaskade.kafka.cluster import Cluster, ClusterService
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


class TestClusterService(TestCase):
    def test_raise_exception_if_config_is_none(self):
        with self.assertRaises(Exception) as context:
            ClusterService(None)

        self.assertEqual("Config not found", str(context.exception))

    def test_raise_exception_if_config_kafka_is_none(self):
        with self.assertRaises(Exception) as context:
            config = MagicMock()
            config.kafka = None
            ClusterService(config)

        self.assertEqual("Config not found", str(context.exception))

    @patch("kaskade.kafka.cluster.AdminClient")
    def test_version_unknown_and_protocol_plain(self, mock_class_client):
        expected_config = {"bootstrap.servers": faker.hostname()}

        config = MagicMock()
        config.kafka = expected_config

        cluster_service = ClusterService(config)

        actual = cluster_service.cluster()

        self.assertEqual("unknown", actual.version)
        self.assertEqual("plain", actual.protocol)

    @patch("kaskade.kafka.cluster.AdminClient")
    def test_has_schemas_false(self, mock_class_client):
        expected_config = {"bootstrap.servers": faker.hostname()}

        config = MagicMock()
        config.kafka = expected_config
        config.schema_registry = None

        cluster_service = ClusterService(config)

        actual = cluster_service.cluster()

        self.assertFalse(actual.has_schemas)

    @patch("kaskade.kafka.cluster.AdminClient")
    def test_has_schemas_true(self, mock_class_client):
        expected_config = {"bootstrap.servers": faker.hostname()}

        config = MagicMock()
        config.kafka = expected_config
        config.schema_registry = faker.pydict()

        cluster_service = ClusterService(config)

        actual = cluster_service.cluster()

        self.assertTrue(actual.has_schemas)

    @patch("kaskade.kafka.cluster.AdminClient")
    def test_protocol(self, mock_class_client):
        protocol = faker.word()
        expected_config = {
            "bootstrap.servers": faker.hostname(),
            "security.protocol": protocol,
        }

        config = MagicMock()
        config.kafka = expected_config
        config.schema_registry = faker.pydict()

        cluster_service = ClusterService(config)

        actual = cluster_service.cluster()

        self.assertEqual(protocol, actual.protocol)

    @patch("kaskade.kafka.cluster.concurrent")
    @patch("kaskade.kafka.cluster.AdminClient")
    def test_get_brokers_in_order(self, mock_class_client, mock_concurrent):
        broker1 = BrokerMetadata()
        broker1.id = 1
        broker2 = BrokerMetadata()
        broker2.id = 2
        broker3 = BrokerMetadata()
        broker3.id = 3

        mock_client = MagicMock()
        mock_client.list_topics.return_value.brokers = {
            broker3.id: broker3,
            broker1.id: broker1,
            broker2.id: broker2,
        }

        mock_class_client.return_value = mock_client

        config = MagicMock()
        expected_config = {"bootstrap.servers": faker.hostname()}
        config.kafka = expected_config
        cluster_service = ClusterService(config)

        actual = cluster_service.cluster().brokers

        self.assertEqual(actual[0], broker1)
        self.assertEqual(actual[1], broker2)
        self.assertEqual(actual[2], broker3)

    @patch("kaskade.kafka.cluster.concurrent")
    @patch("kaskade.kafka.cluster.ConfigResource")
    @patch("kaskade.kafka.cluster.AdminClient")
    def test_get_version_from_config(
        self, mock_class_client, mock_class_config_resource, mock_concurrent
    ):
        broker1 = BrokerMetadata()
        broker1.id = 1
        broker2 = BrokerMetadata()
        broker2.id = 2
        broker3 = BrokerMetadata()
        broker3.id = 3

        mock_client = MagicMock()
        mock_client.list_topics.return_value.brokers = {
            broker3.id: broker3,
            broker1.id: broker1,
            broker2.id: broker2,
        }

        mock_class_client.return_value = mock_client

        expected_config = {"bootstrap.servers": faker.hostname()}
        expected_version = faker.bothify("#.#.#")
        mock_version = "{}-{}".format(expected_version, faker.word())
        config_entry = ConfigEntry("inter.broker.protocol.version", mock_version)

        config = MagicMock()
        config.kafka = expected_config

        kafka = ClusterService(config)

        mock_task = MagicMock()
        mock_task.result = MagicMock(
            return_value={"inter.broker.protocol.version": config_entry}
        )
        mock_concurrent.futures.as_completed.return_value = iter([mock_task])

        actual = kafka.cluster()

        mock_class_client.assert_called_once_with(expected_config)
        mock_class_config_resource.assert_called_once_with(
            confluent_kafka.admin.RESOURCE_BROKER, str(broker1.id)
        )
        mock_class_client.return_value.describe_configs.assert_called_once_with(
            [mock_class_config_resource.return_value]
        )
        self.assertEqual(expected_version, actual.version)

    @patch("kaskade.kafka.cluster.concurrent")
    @patch("kaskade.kafka.cluster.AdminClient")
    def test_get_unknown_version_if_config_does_not_exists(
        self, mock_class_client, mock_concurrent
    ):
        mock_client = MagicMock()
        mock_client.list_topics.return_value.brokers = {1: MagicMock()}

        mock_class_client.return_value = mock_client

        expected_config = {"bootstrap.servers": faker.hostname()}

        config = MagicMock()
        config.kafka = expected_config

        kafka = ClusterService(config)

        mock_task = MagicMock()
        mock_task.result = MagicMock(return_value=faker.pydict())
        mock_concurrent.futures.as_completed.return_value = iter([mock_task])

        actual = kafka.cluster()

        self.assertEqual("unknown", actual.version)

    @patch("kaskade.kafka.cluster.concurrent")
    @patch("kaskade.kafka.cluster.AdminClient")
    def test_get_unknown_version_if_tasks_is_none(
        self, mock_class_client, mock_concurrent
    ):

        mock_client = MagicMock()
        mock_client.list_topics.return_value.brokers = {1: MagicMock()}

        mock_class_client.return_value = mock_client

        expected_config = {"bootstrap.servers": faker.hostname()}

        config = MagicMock()
        config.kafka = expected_config

        kafka = ClusterService(config)

        mock_task = MagicMock()
        mock_task.result = MagicMock(return_value=None)
        mock_concurrent.futures.as_completed.return_value = iter([mock_task])

        actual = kafka.cluster()

        self.assertEqual("unknown", actual.version)
