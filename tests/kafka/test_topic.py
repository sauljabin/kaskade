from unittest import TestCase
from unittest.mock import MagicMock, patch

from confluent_kafka.admin import TopicMetadata

from kaskade.kafka.topic import Topic, TopicService
from tests import faker


class TestTopic(TestCase):
    def test_str(self):
        random_name = faker.word()
        topic = Topic(name=random_name)

        self.assertEqual(random_name, str(topic))


class TestTopicService(TestCase):
    @patch("kaskade.kafka.topic.GroupService")
    @patch("kaskade.kafka.topic.AdminClient")
    def test_get_topics_from_client(self, mock_class_client, mock_class_group_service):
        config = MagicMock()
        expected_config = {"bootstrap.servers": faker.hostname()}
        config.kafka = expected_config
        topic_service = TopicService(config)

        topic_service.topics()

        mock_class_client.assert_called_once_with(expected_config)

    def test_raise_exception_if_config_is_none(self):
        with self.assertRaises(Exception) as context:
            TopicService(None)

        self.assertEqual("Config not found", str(context.exception))

    def test_raise_exception_if_config_kafka_is_none(self):
        with self.assertRaises(Exception) as context:
            config = MagicMock()
            config.kafka = None
            TopicService(config)

        self.assertEqual("Config not found", str(context.exception))

    @patch("kaskade.kafka.topic.GroupService")
    @patch("kaskade.kafka.topic.AdminClient")
    def test_get_topics_as_a_list_of_topics(
        self, mock_class_client, mock_class_group_service
    ):
        topic = TopicMetadata()
        topic.topic = "topic"
        topic.partitions = faker.pydict()

        mock_client = MagicMock()
        mock_client.list_topics.return_value.topics = {topic.topic: topic}

        mock_class_client.return_value = mock_client

        config = MagicMock()
        expected_config = {"bootstrap.servers": faker.hostname()}
        config.kafka = expected_config

        topic_service = TopicService(config)

        actual = topic_service.topics()

        mock_class_client.assert_called_once_with(expected_config)
        self.assertIsInstance(actual, list)
        self.assertEqual(list(topic.partitions.values()), actual[0].partitions)
        self.assertIsInstance(actual[0], Topic)

    @patch("kaskade.kafka.topic.GroupService")
    @patch("kaskade.kafka.topic.AdminClient")
    def test_get_topics_in_order(self, mock_class_client, mock_class_group_service):
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
        topic_service = TopicService(config)

        actual = topic_service.topics()

        self.assertEqual(actual[0].name, topic1.topic)
        self.assertEqual(actual[1].name, topic2.topic)
        self.assertEqual(actual[2].name, topic3.topic)
