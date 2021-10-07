from unittest import TestCase
from unittest.mock import MagicMock, call, patch

from kaskade.renderables.kafka_info import KafkaInfo
from tests import faker


class TestKafkaInfo(TestCase):
    def test_string(self):
        expected = str(
            {
                "kafka": "unknown",
                "brokers": "unknown",
                "schemas": "no",
                "protocol": "plain",
            }
        )
        actual = str(KafkaInfo())

        self.assertEqual(expected, actual)

    @patch("kaskade.renderables.kafka_info.Table")
    def test_render_kafka_info_in_a_table(self, mock_class_table):
        mock_table = MagicMock()
        mock_class_table.return_value = mock_table

        kafka_version = faker.bothify("#.#")
        total_brokers = faker.pyint()
        has_schemas = True
        protocol = faker.word().upper()

        kafka_info = KafkaInfo(
            kafka_version=kafka_version,
            total_brokers=total_brokers,
            has_schemas=has_schemas,
            protocol=protocol,
        )

        actual = kafka_info.__rich__()

        self.assertEqual(mock_table, actual)
        mock_class_table.assert_called_with(box=None, expand=False)
        mock_table.add_column.assert_has_calls([call(style="bold blue"), call()])

        mock_table.add_row.assert_has_calls(
            [
                call("kafka:", kafka_version),
                call("brokers:", str(total_brokers)),
                call("schemas:", "yes"),
                call("protocol:", protocol.lower()),
            ]
        )

    @patch("kaskade.renderables.kafka_info.Table")
    def test_render_kafka_info_in_a_table_and_print_no_if_schames_is_false(
        self, mock_class_table
    ):
        mock_table = MagicMock()
        mock_class_table.return_value = mock_table

        has_schemas = False

        kafka_info = KafkaInfo(
            has_schemas=has_schemas,
        )

        kafka_info.__rich__()

        mock_table.add_row.assert_has_calls(
            [
                call("schemas:", "no"),
            ]
        )
