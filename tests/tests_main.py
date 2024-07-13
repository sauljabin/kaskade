import unittest
from unittest.mock import patch

from click.testing import CliRunner

from kaskade.main import cli


class AdminCli(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.command = "admin"

    def test_bootstrap_server_required(self):
        result = self.runner.invoke(cli, [self.command])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-b'", result.output)

    def test_invalid_extra_kafka_config(self):
        result = self.runner.invoke(cli, [self.command, "-x", "property.name"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '-x': Should be property=value", result.output)

    @patch("kaskade.main.KaskadeAdmin")
    def test_update_kafka_config(self, mock_class_kaskade_admin):
        expected_server = "localhost:9092"

        result = self.runner.invoke(cli, [self.command, "-b", expected_server])

        mock_class_kaskade_admin.assert_called_with({"bootstrap.servers": expected_server})
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeAdmin")
    def test_update_kafka_config_with_extra_config(self, mock_class_kaskade_admin):
        expected_server = "localhost:9092"
        expected_property_name = "property.name"
        expected_property_value = "property.value"

        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                expected_server,
                "-x",
                f"{expected_property_name}={expected_property_value}",
            ],
        )

        mock_class_kaskade_admin.assert_called_with(
            {"bootstrap.servers": expected_server, expected_property_name: expected_property_value}
        )
        self.assertEqual(0, result.exit_code)


class ConsumerCli(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.command = "consumer"

    def test_bootstrap_server_required(self):
        result = self.runner.invoke(cli, [self.command])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-b'", result.output)

    def test_invalid_extra_kafka_config(self):
        result = self.runner.invoke(cli, [self.command, "-x", "property.name"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '-x': Should be property=value", result.output)
