import unittest
from unittest.mock import patch

from click.testing import CliRunner

from kaskade.main import cli
from kaskade.models import Format
from tests import faker

EXPECTED_TOPIC = "my.topic"

BOOTSTRAP_SERVERS = "bootstrap.servers"
EXPECTED_SERVER = "localhost:9092"


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
        result = self.runner.invoke(cli, [self.command, "-b", EXPECTED_SERVER])

        mock_class_kaskade_admin.assert_called_with({BOOTSTRAP_SERVERS: EXPECTED_SERVER})
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeAdmin")
    def test_update_kafka_config_with_extra_config(self, mock_class_kaskade_admin):
        expected_property_name = "property.name"
        expected_property_value = "property.value"

        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-x",
                f"{expected_property_name}={expected_property_value}",
            ],
        )

        mock_class_kaskade_admin.assert_called_with(
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER, expected_property_name: expected_property_value}
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeAdmin")
    def test_update_kafka_config_with_multiple_extra_config(self, mock_class_kaskade_admin):
        expected_property_name = "property.name"
        expected_property_value = "property.value"
        expected_property_name2 = "property.name2"
        expected_property_value2 = "property.value2="

        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-x",
                f"{expected_property_name}={expected_property_value}",
                "-x",
                f"{expected_property_name2}={expected_property_value2}",
            ],
        )

        mock_class_kaskade_admin.assert_called_with(
            {
                BOOTSTRAP_SERVERS: EXPECTED_SERVER,
                expected_property_name: expected_property_value,
                expected_property_name2: expected_property_value2,
            }
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

    def test_topic_required(self):
        result = self.runner.invoke(cli, [self.command, "-b", EXPECTED_SERVER])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-t'", result.output)

    def test_invalid_extra_kafka_config(self):
        result = self.runner.invoke(cli, [self.command, "-x", "property.name"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '-x': Should be property=value", result.output)

    def test_invalid_schema_registry_config(self):
        result = self.runner.invoke(cli, [self.command, "-s", "property.name"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '-s': Should be property=value", result.output)

    def test_validate_schema_registry_url(self):
        result = self.runner.invoke(
            cli,
            [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC, "-s", "not.valid=property"],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-s url=<my url>'", result.output)

    def test_validate_schema_registry_format(self):
        result = self.runner.invoke(
            cli,
            [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC, "-s", "url=http://my-url"],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-k avro' and/or '-v avro'", result.output)

    def test_validate_schema_registry_is_needed_with_avro_key(self):
        result = self.runner.invoke(
            cli, [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC, "-k", "avro"]
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-s'", result.output)

    def test_validate_schema_registry_is_needed_with_avro_value(self):
        result = self.runner.invoke(
            cli, [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC, "-v", "avro"]
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-s'", result.output)

    @patch("kaskade.main.KaskadeConsumer")
    def test_update_kafka_config(self, mock_class_kaskade_consumer):
        result = self.runner.invoke(
            cli, [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC]
        )

        mock_class_kaskade_consumer.assert_called_with(
            EXPECTED_TOPIC, {BOOTSTRAP_SERVERS: EXPECTED_SERVER}, {}, Format.BYTES, Format.BYTES
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeConsumer")
    def test_pass_right_format(self, mock_class_kaskade_consumer):
        options = ["long", "bytes", "string"]

        expected_key_format = faker.random.choice(options)
        expected_value_format = faker.random.choice(options)

        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-k",
                expected_key_format,
                "-v",
                expected_value_format,
            ],
        )

        mock_class_kaskade_consumer.assert_called_with(
            EXPECTED_TOPIC,
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER},
            {},
            Format.from_str(expected_key_format),
            Format.from_str(expected_value_format),
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeConsumer")
    def test_update_kafka_config_with_extra_config(self, mock_class_kaskade_consumer):
        expected_property_name = "property.name"
        expected_property_value = "property.value"

        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-x",
                f"{expected_property_name}={expected_property_value}",
            ],
        )

        mock_class_kaskade_consumer.assert_called_with(
            EXPECTED_TOPIC,
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER, expected_property_name: expected_property_value},
            {},
            Format.BYTES,
            Format.BYTES,
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeConsumer")
    def test_update_kafka_config_with_multiple_extra_config(self, mock_class_kaskade_consumer):
        expected_property_name = "property.name"
        expected_property_value = "property.value"
        expected_property_name2 = "property.name2"
        expected_property_value2 = "property.value2="

        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-x",
                f"{expected_property_name}={expected_property_value}",
                "-x",
                f"{expected_property_name2}={expected_property_value2}",
            ],
        )

        mock_class_kaskade_consumer.assert_called_with(
            EXPECTED_TOPIC,
            {
                BOOTSTRAP_SERVERS: EXPECTED_SERVER,
                expected_property_name: expected_property_value,
                expected_property_name2: expected_property_value2,
            },
            {},
            Format.BYTES,
            Format.BYTES,
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeConsumer")
    def test_pass_schema_registry_configs(self, mock_class_kaskade_consumer):
        expected_property_name = "url"
        expected_property_value = "property.value"
        expected_property_name2 = "property.name2"
        expected_property_value2 = "property.value2="

        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-s",
                f"{expected_property_name}={expected_property_value}",
                "-s",
                f"{expected_property_name2}={expected_property_value2}",
                "-k",
                "avro",
                "-v",
                "avro",
            ],
        )

        mock_class_kaskade_consumer.assert_called_with(
            EXPECTED_TOPIC,
            {
                BOOTSTRAP_SERVERS: EXPECTED_SERVER,
            },
            {
                expected_property_name: expected_property_value,
                expected_property_name2: expected_property_value2,
            },
            Format.AVRO,
            Format.AVRO,
        )
        self.assertEqual(0, result.exit_code)
