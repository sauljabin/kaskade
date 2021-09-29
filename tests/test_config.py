from unittest import TestCase
from unittest.mock import MagicMock, mock_open, patch

from kaskade.config import Config
from tests import faker

kaskade_yaml = """
kafka:
    bootstrap.servers: kafka:9092

kaskade:
    example: test
"""


class TestConfig(TestCase):
    @patch("kaskade.config.Path")
    @patch("builtins.open", new_callable=mock_open, read_data=kaskade_yaml)
    def test_load_default_file_if_receive_empty_path(
        self, mock_open_file, mock_class_path
    ):
        mock_class_path.return_value.exists = MagicMock(
            side_effect=[True, False, False, True]
        )
        config = Config(None)
        mock_open_file.assert_called_once_with("kaskade.yml", "r")
        self.assertEqual(config.text, kaskade_yaml)
        self.assertEqual(
            config.yaml,
            {
                "kafka": {"bootstrap.servers": "kafka:9092"},
                "kaskade": {"example": "test"},
            },
        )
        self.assertEqual(config.kafka, {"bootstrap.servers": "kafka:9092"})
        self.assertEqual(config.kaskade, {"example": "test"})

    @patch("kaskade.config.Path")
    @patch("builtins.open", new_callable=mock_open, read_data=kaskade_yaml)
    def test_load_file_from_arg(self, mock_open_file, mock_class_path):
        random_file = faker.file_path(extension="yml")
        mock_class_path.return_value.exists = MagicMock(
            side_effect=[True, False, True, False, False]
        )
        config = Config(random_file)
        mock_open_file.assert_called_once_with(random_file, "r")
        self.assertEqual(config.text, kaskade_yaml)

    @patch("kaskade.config.Path")
    @patch("builtins.open", new_callable=mock_open, read_data=kaskade_yaml)
    def test_load_default_file_if_receive_empty_path_and_default_does_not_exists(
        self, mock_open_file, mock_class_path
    ):
        mock_class_path.return_value.exists = MagicMock(
            side_effect=[False, False, False, True]
        )
        config = Config(None)
        mock_open_file.assert_called_once_with("config.yaml", "r")
        self.assertEqual(config.text, kaskade_yaml)

    @patch("kaskade.config.Path")
    def test_raise_exception_if_does_not_find_any_file(self, mock_class_path):
        mock_class_path.return_value.exists = MagicMock(
            side_effect=[False, False, False, False]
        )
        with self.assertRaises(Exception) as test_context:
            Config(None)
        self.assertEqual(
            "Default config file kaskade.yml, kaskade.yaml, "
            "config.yml or config.yaml not found",
            str(test_context.exception),
        )

    @patch("kaskade.config.Path")
    def test_raise_exception_if_does_not_find_any_file_and_receive_one(
        self, mock_class_path
    ):
        random_file = faker.file_path(extension="yml")
        mock_class_path.return_value.exists = MagicMock(return_value=False)
        with self.assertRaises(Exception) as test_context:
            Config(random_file)
        self.assertEqual(
            f"Config file {random_file} not found",
            str(test_context.exception),
        )
