from unittest import TestCase
from unittest.mock import MagicMock, patch

from confluent_kafka.admin import PartitionMetadata, TopicMetadata

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
        config = {"bootstrap.servers": faker.hostname()}
        kafka = Kafka(config)

        kafka.topics()

        mock_class_client.assert_called_once_with(config)

    @patch("kaskade.kafka.AdminClient")
    def test_get_topics_as_a_list_of_topics(self, mock_class_client):
        topic = TopicMetadata()
        topic.topic = "topic"

        mock_client = MagicMock()
        mock_client.list_topics.return_value.topics = {topic.topic: topic}

        mock_class_client.return_value = mock_client

        config = {"bootstrap.servers": faker.hostname()}
        kafka = Kafka(config)

        actual = kafka.topics()

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

        config = {"bootstrap.servers": faker.hostname()}
        kafka = Kafka(config)

        actual = kafka.topics()

        self.assertEqual(actual[0].name, topic1.topic)
        self.assertEqual(actual[1].name, topic2.topic)
        self.assertEqual(actual[2].name, topic3.topic)
