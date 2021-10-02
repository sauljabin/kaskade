from unittest import TestCase
from unittest.mock import MagicMock, patch

import confluent_kafka
from confluent_kafka.admin import (
    BrokerMetadata,
    ConfigEntry,
    PartitionMetadata,
    TopicMetadata,
)

from kaskade.kafka import Kafka, Topic
from tests import faker


class TestTopic(TestCase):
    def test_get_name(self):
        metadata = TopicMetadata()
        metadata.topic = faker.word()

        topic = Topic(metadata)

        self.assertEqual(metadata.topic, topic.name)
        self.assertEqual(metadata.topic, str(topic))
        self.assertEqual(metadata.topic, topic.__str__())

    def test_get_partitions_data_as_list(self):
        metadata = TopicMetadata()
        partition0 = PartitionMetadata()
        partition1 = PartitionMetadata()
        metadata.partitions = {"0": partition0, "1": partition1}

        topic = Topic(metadata)

        topic_partitions = topic.partitions()
        self.assertIsInstance(topic_partitions, list)
        self.assertEqual(2, len(topic_partitions))
        self.assertEqual(partition0, topic_partitions[0])
        self.assertEqual(partition1, topic_partitions[1])


class TestKafka(TestCase):
    @patch("kaskade.kafka.AdminClient")
    def test_get_topics_from_client(self, mock_class_client):
        config = MagicMock()
        expected_config = {"bootstrap.servers": faker.hostname()}
        config.kafka = expected_config
        kafka = Kafka(config)

        kafka.topics()

        mock_class_client.assert_called_once_with(expected_config)

    def test_return_empty_topics_list_if_config_is_none(self):
        kafka = Kafka(None)

        actual = kafka.topics()

        self.assertEqual(0, len(actual))

    def test_return_empty_topics_list_if_config_kafka_is_none(self):
        config = MagicMock()
        config.kafka = None
        kafka = Kafka(config)

        actual = kafka.topics()

        self.assertEqual(0, len(actual))

    @patch("kaskade.kafka.AdminClient")
    def test_get_topics_as_a_list_of_topics(self, mock_class_client):
        topic = TopicMetadata()
        topic.topic = "topic"

        mock_client = MagicMock()
        mock_client.list_topics.return_value.topics = {topic.topic: topic}

        mock_class_client.return_value = mock_client

        config = MagicMock()
        expected_config = {"bootstrap.servers": faker.hostname()}
        config.kafka = expected_config

        kafka = Kafka(config)

        actual = kafka.topics()

        mock_class_client.assert_called_once_with(expected_config)
        self.assertIsInstance(actual, list)
        self.assertIsInstance(actual[0], Topic)

    @patch("kaskade.kafka.AdminClient")
    def test_get_topics_in_order(self, mock_class_client):
        topic1 = TopicMetadata()
        topic1.topic = "topic1"
        topic2 = TopicMetadata()
        topic2.topic = "topic2"
        topic3 = TopicMetadata()
        topic3.topic = "topic3"

        mock_client = MagicMock()
        mock_client.list_topics.return_value.topics = {
            topic3.topic: topic3,
            topic1.topic: topic1,
            topic2.topic: topic2,
        }

        mock_class_client.return_value = mock_client

        config = MagicMock()
        expected_config = {"bootstrap.servers": faker.hostname()}
        config.kafka = expected_config
        kafka = Kafka(config)

        actual = kafka.topics()

        self.assertEqual(actual[0].name, topic1.topic)
        self.assertEqual(actual[1].name, topic2.topic)
        self.assertEqual(actual[2].name, topic3.topic)

    def test_get_protocol_plain(self):
        config = MagicMock()
        expected_config = {"bootstrap.servers": faker.hostname()}
        config.kafka = expected_config

        kafka = Kafka(config)

        self.assertEqual("plain", kafka.protocol())

    def test_get_protocol_plain_if_config_is_none(self):
        kafka = Kafka(None)

        self.assertEqual("plain", kafka.protocol())

    def test_get_protocol_plain_config_kafka_is_none(self):
        config = MagicMock()
        config.kafka = None

        kafka = Kafka(config)

        self.assertEqual("plain", kafka.protocol())

    def test_get_protocol(self):
        config = MagicMock()
        expected_config = {
            "bootstrap.servers": faker.hostname(),
            "security.protocol": faker.word().upper(),
        }
        config.kafka = expected_config

        kafka = Kafka(config)

        self.assertEqual(expected_config["security.protocol"].lower(), kafka.protocol())

    def test_has_schemas_true(self):
        config = MagicMock()
        config.schema_registry = faker.pydict(nb_elements=1, variable_nb_elements=False)

        kafka = Kafka(config)

        self.assertTrue(kafka.has_schemas())

    def test_has_schemas_false(self):
        config = MagicMock()
        config.schema_registry = None

        kafka = Kafka(config)

        self.assertFalse(kafka.has_schemas())

    def test_has_schemas_false_if_config_is_none(self):
        kafka = Kafka(None)

        self.assertFalse(kafka.has_schemas())

    @patch("kaskade.kafka.AdminClient")
    def test_get_brokers_from_client(self, mock_class_client):
        config = MagicMock()
        expected_config = {"bootstrap.servers": faker.hostname()}
        config.kafka = expected_config
        kafka = Kafka(config)

        kafka.brokers()

        mock_class_client.assert_called_once_with(expected_config)

    def test_return_empty_brokers_list_if_config_is_none(self):
        kafka = Kafka(None)

        actual = kafka.brokers()

        self.assertEqual(0, len(actual))

    def test_return_empty_brokers_list_if_config_kafka_is_none(self):
        config = MagicMock()
        config.kafka = None
        kafka = Kafka(config)

        actual = kafka.brokers()

        self.assertEqual(0, len(actual))

    @patch("kaskade.kafka.AdminClient")
    def test_get_brokers_as_a_list_of_brokers(self, mock_class_client):
        broker = BrokerMetadata()
        broker.id = faker.pyint()
        broker.host = faker.hostname()
        broker.port = faker.port_number()

        mock_client = MagicMock()
        mock_client.list_topics.return_value.brokers = {broker.id: broker}

        mock_class_client.return_value = mock_client

        config = MagicMock()
        expected_config = {"bootstrap.servers": faker.hostname()}
        config.kafka = expected_config

        kafka = Kafka(config)

        actual = kafka.brokers()

        mock_class_client.assert_called_once_with(expected_config)
        self.assertIsInstance(actual, list)

    @patch("kaskade.kafka.AdminClient")
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
        kafka = Kafka(config)

        actual = kafka.brokers()

        self.assertEqual(actual[0], broker1)
        self.assertEqual(actual[1], broker2)
        self.assertEqual(actual[2], broker3)

    def test_return_unknown_version_if_config_is_none(self):
        kafka = Kafka(None)

        actual = kafka.version()

        self.assertEqual("unknown", actual)

    def test_return_unknown_version_if_config_kafka_is_none(self):
        config = MagicMock()
        config.kafka = None
        kafka = Kafka(config)

        actual = kafka.version()

        self.assertEqual("unknown", actual)

    def test_return_unknown_version_if_brokers_is_empty(self):
        config = MagicMock()
        expected_config = {"bootstrap.servers": faker.hostname()}
        config.kafka = expected_config
        kafka = Kafka(config)
        kafka.brokers = MagicMock(return_value=[])
        actual = kafka.version()

        self.assertEqual("unknown", actual)

    @patch("kaskade.kafka.concurrent")
    @patch("kaskade.kafka.ConfigResource")
    @patch("kaskade.kafka.AdminClient")
    def test_get_version_from_config(
        self, mock_class_client, mock_class_config_resource, mock_concurrent
    ):
        expected_config = {"bootstrap.servers": faker.hostname()}
        expected_version = faker.bothify("#.#.#")
        mock_version = "{}-{}".format(expected_version, faker.word())
        config_entry = ConfigEntry("inter.broker.protocol.version", mock_version)

        config = MagicMock()
        config.kafka = expected_config

        kafka = Kafka(config)
        broker_metadata = BrokerMetadata()
        broker_metadata.id = faker.pyint()
        kafka.brokers = MagicMock(return_value=[broker_metadata])

        mock_task = MagicMock()
        mock_task.result = MagicMock(
            return_value={"inter.broker.protocol.version": config_entry}
        )
        mock_concurrent.futures.as_completed.return_value = iter([mock_task])

        actual = kafka.version()

        mock_class_client.assert_called_once_with(expected_config)
        mock_class_config_resource.assert_called_once_with(
            confluent_kafka.admin.RESOURCE_BROKER, str(broker_metadata.id)
        )
        mock_class_client.return_value.describe_configs.assert_called_once_with(
            [mock_class_config_resource.return_value]
        )
        self.assertEqual(expected_version, actual)

    @patch("kaskade.kafka.concurrent")
    @patch("kaskade.kafka.ConfigResource")
    @patch("kaskade.kafka.AdminClient")
    def test_get_default_version_if_future_config_does_not_exist(
        self, mock_class_client, mock_class_config_resource, mock_concurrent
    ):
        expected_config = {"bootstrap.servers": faker.hostname()}

        config = MagicMock()
        config.kafka = expected_config

        kafka = Kafka(config)
        broker_metadata = BrokerMetadata()
        broker_metadata.id = faker.pyint()
        kafka.brokers = MagicMock(return_value=[broker_metadata])

        mock_task = MagicMock()
        mock_task.result = MagicMock(return_value=faker.pydict())
        mock_concurrent.futures.as_completed.return_value = iter([mock_task])

        actual = kafka.version()

        mock_class_client.assert_called_once_with(expected_config)
        mock_class_config_resource.assert_called_once_with(
            confluent_kafka.admin.RESOURCE_BROKER, str(broker_metadata.id)
        )
        mock_class_client.return_value.describe_configs.assert_called_once_with(
            [mock_class_config_resource.return_value]
        )
        self.assertEqual("unknown", actual)

    @patch("kaskade.kafka.concurrent")
    @patch("kaskade.kafka.ConfigResource")
    @patch("kaskade.kafka.AdminClient")
    def test_get_default_version_if_future_result_does_not_exist(
        self, mock_class_client, mock_class_config_resource, mock_concurrent
    ):
        expected_config = {"bootstrap.servers": faker.hostname()}

        config = MagicMock()
        config.kafka = expected_config

        kafka = Kafka(config)
        broker_metadata = BrokerMetadata()
        broker_metadata.id = faker.pyint()
        kafka.brokers = MagicMock(return_value=[broker_metadata])

        mock_task = MagicMock()
        mock_task.result = MagicMock(return_value=None)
        mock_concurrent.futures.as_completed.return_value = iter([mock_task])

        actual = kafka.version()

        mock_class_client.assert_called_once_with(expected_config)
        mock_class_config_resource.assert_called_once_with(
            confluent_kafka.admin.RESOURCE_BROKER, str(broker_metadata.id)
        )
        mock_class_client.return_value.describe_configs.assert_called_once_with(
            [mock_class_config_resource.return_value]
        )
        self.assertEqual("unknown", actual)
