from unittest import TestCase
from unittest.mock import MagicMock, patch

import confluent_kafka
from confluent_kafka.admin import BrokerMetadata, ConfigEntry

from kaskade.kafka.cluster_service import ClusterService
from tests import faker


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

    @patch("kaskade.kafka.cluster_service.AdminClient")
    def test_version_unknown_and_protocol_plain(self, mock_class_client):
        expected_config = {"bootstrap.servers": faker.hostname()}

        config = MagicMock()
        config.kafka = expected_config

        cluster_service = ClusterService(config)

        actual = cluster_service.current()

        self.assertEqual("unknown", actual.version)
        self.assertEqual("plain", actual.protocol)

    @patch("kaskade.kafka.cluster_service.AdminClient")
    def test_has_schemas_false(self, mock_class_client):
        expected_config = {"bootstrap.servers": faker.hostname()}

        config = MagicMock()
        config.kafka = expected_config
        config.schema_registry = None

        cluster_service = ClusterService(config)

        actual = cluster_service.current()

        self.assertFalse(actual.has_schemas)

    @patch("kaskade.kafka.cluster_service.AdminClient")
    def test_has_schemas_true(self, mock_class_client):
        expected_config = {"bootstrap.servers": faker.hostname()}

        config = MagicMock()
        config.kafka = expected_config
        config.schema_registry = faker.pydict()

        cluster_service = ClusterService(config)

        actual = cluster_service.current()

        self.assertTrue(actual.has_schemas)

    @patch("kaskade.kafka.cluster_service.AdminClient")
    def test_protocol(self, mock_class_client):
        protocol = faker.word().upper()
        expected_config = {
            "bootstrap.servers": faker.hostname(),
            "security.protocol": protocol,
        }

        config = MagicMock()
        config.kafka = expected_config
        config.schema_registry = faker.pydict()

        cluster_service = ClusterService(config)

        actual = cluster_service.current()

        self.assertEqual(protocol.lower(), actual.protocol)

    @patch("kaskade.kafka.cluster_service.AdminClient")
    def test_get_brokers_in_order(self, mock_class_client):
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

        config_entry = ConfigEntry("inter.broker.protocol.version", "")
        mock_task = MagicMock()
        mock_task.result = MagicMock(
            return_value={"inter.broker.protocol.version": config_entry}
        )

        mock_client.describe_configs.return_value = {1: mock_task}

        actual = cluster_service.current().brokers

        self.assertEqual(actual[0].id, broker1.id)
        self.assertEqual(actual[1].id, broker2.id)
        self.assertEqual(actual[2].id, broker3.id)

    @patch("kaskade.kafka.cluster_service.ConfigResource")
    @patch("kaskade.kafka.cluster_service.AdminClient")
    def test_get_version_from_config(
        self, mock_class_client, mock_class_config_resource
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

        mock_client.describe_configs.return_value = {1: mock_task}

        actual = kafka.current()

        mock_class_client.assert_called_once_with(expected_config)
        mock_class_config_resource.assert_called_once_with(
            confluent_kafka.admin.RESOURCE_BROKER, str(broker1.id)
        )
        self.assertEqual(expected_version, actual.version)

    @patch("kaskade.kafka.cluster_service.AdminClient")
    def test_get_unknown_version_if_config_does_not_exists(self, mock_class_client):
        mock_client = MagicMock()
        mock_client.list_topics.return_value.brokers = {1: MagicMock()}

        mock_class_client.return_value = mock_client

        expected_config = {"bootstrap.servers": faker.hostname()}

        config = MagicMock()
        config.kafka = expected_config

        kafka = ClusterService(config)

        mock_task = MagicMock()
        mock_task.result = MagicMock(return_value=faker.pydict())

        mock_client.describe_configs.return_value = {1: mock_task}

        actual = kafka.current()

        self.assertEqual("unknown", actual.version)

    @patch("kaskade.kafka.cluster_service.AdminClient")
    def test_get_unknown_version_if_result_is_none(self, mock_class_client):
        mock_client = MagicMock()
        mock_client.list_topics.return_value.brokers = {1: MagicMock()}

        mock_class_client.return_value = mock_client

        expected_config = {"bootstrap.servers": faker.hostname()}

        config = MagicMock()
        config.kafka = expected_config

        kafka = ClusterService(config)

        mock_task = MagicMock()
        mock_task.result.return_value = None

        mock_client.describe_configs.return_value = {1: mock_task}

        actual = kafka.current()

        self.assertEqual("unknown", actual.version)
