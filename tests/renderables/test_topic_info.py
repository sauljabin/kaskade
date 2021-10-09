from unittest import TestCase
from unittest.mock import MagicMock, call, patch

from kaskade.renderables.topic_info import TopicInfo
from tests import faker


class TestTopicInfo(TestCase):
    def test_string(self):
        expected = str(
            {
                "name": "unknown",
                "partitions": "unknown",
            }
        )
        actual = str(TopicInfo())

        self.assertEqual(expected, actual)

    @patch("kaskade.renderables.topic_info.Table")
    def test_render_kafka_info_in_a_table(self, mock_class_table):
        mock_table = MagicMock()
        mock_class_table.return_value = mock_table

        name = faker.word()
        partitions = faker.word()

        topic_info = TopicInfo(
            name=name,
            partitions=partitions,
        )

        actual = topic_info.__rich__()

        self.assertEqual(mock_table, actual)
        mock_class_table.assert_called_with(
            box=None, expand=False, show_header=False, show_edge=False
        )
        mock_table.add_column.assert_has_calls(
            [call(style="magenta bold"), call(style="yellow bold")]
        )

        mock_table.add_row.assert_has_calls(
            [
                call("name:", name),
                call("partitions:", partitions.lower()),
            ]
        )
