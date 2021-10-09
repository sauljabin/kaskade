from unittest import TestCase
from unittest.mock import PropertyMock, patch

from rich.columns import Columns

from kaskade.renderables.kafka_info import KafkaInfo
from kaskade.renderables.kaskade_name import KaskadeName
from kaskade.renderables.shortcuts import Shortcuts
from kaskade.widgets.header import Header
from tests import faker


class TestHeader(TestCase):
    @patch("kaskade.widgets.header.Header.app", new_callable=PropertyMock)
    def test_size(self, mock_app):
        header = Header()

        header.on_mount()

        self.assertEqual(6, header.layout_size)

    @patch("kaskade.widgets.header.Header.app", new_callable=PropertyMock)
    def test_renderables(self, mock_app):
        header = Header()

        header.on_mount()
        actual = header.render()

        self.assertEqual(3, actual.padding)
        self.assertIsInstance(actual, Columns)
        self.assertIsInstance(actual.renderables[0], KaskadeName)
        self.assertIsInstance(actual.renderables[1], KafkaInfo)
        self.assertIsInstance(actual.renderables[2], Shortcuts)

    @patch("kaskade.widgets.header.KafkaInfo")
    @patch("kaskade.widgets.header.Header.app", new_callable=PropertyMock)
    def test_kafka_info_setup(self, mock_app, mock_class_kafka_info):
        kafka_version = faker.bothify("#.#")
        mock_app.return_value.cluster.version.return_value = kafka_version

        total_brokers = faker.pylist()
        mock_app.return_value.cluster.brokers.return_value = total_brokers

        has_schemas = faker.pybool()
        mock_app.return_value.cluster.has_schemas.return_value = has_schemas

        protocol = faker.word()
        mock_app.return_value.cluster.protocol.return_value = protocol
        header = Header()

        header.on_mount()
        header.render()

        mock_class_kafka_info.assert_called_once_with(
            kafka_version=kafka_version,
            total_brokers=len(total_brokers),
            has_schemas=has_schemas,
            protocol=protocol,
        )
