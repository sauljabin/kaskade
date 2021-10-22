from unittest import TestCase

from rich.text import Text

from kaskade.renderables.topic_info import TopicInfo
from tests.kafka import random_topic


class TestTopicInfo(TestCase):
    def test_string(self):
        topic = random_topic()
        expected = str(topic)
        actual = str(TopicInfo(topic))

        self.assertEqual(expected, actual)

    def test_render_kafka_info_in_a_table(self):
        topic = random_topic()
        topic_info = TopicInfo(topic)

        actual = topic_info.__rich__()

        topic_name = actual.renderables[0]
        self.assertEqual(" name: " + topic.name, Text.from_markup(topic_name).plain)

        topic_table = actual.renderables[1]
        cells_label = topic_table.columns[0].cells
        cells_values = topic_table.columns[1].cells
        self.assertEqual("partitions:", next(cells_label))
        self.assertEqual(str(topic.partitions_count()), next(cells_values))
        self.assertEqual("replicas:", next(cells_label))
        self.assertEqual(str(topic.replicas_count()), next(cells_values))

        cells_label = topic_table.columns[2].cells
        cells_values = topic_table.columns[3].cells
        self.assertEqual("groups:", next(cells_label))
        self.assertEqual(str(topic.groups_count()), next(cells_values))
        self.assertEqual("in sync:", next(cells_label))
        self.assertEqual(str(topic.isrs_count()), next(cells_values))
