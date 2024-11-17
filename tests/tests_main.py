import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from kaskade.main import cli
from kaskade.deserializers import Format
from tests import faker

EXPECTED_TOPIC = "my.topic"
BOOTSTRAP_SERVERS = "bootstrap.servers"
EXPECTED_SERVER = "localhost:9092"


class TestAdminCli(unittest.TestCase):
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


class TestConsumerCli(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.command = "consumer"
        self.temp_descriptor = tempfile.NamedTemporaryFile()

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

    def test_invalid_protobuf_config(self):
        result = self.runner.invoke(cli, [self.command, "-p", "property.name"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '-p': Should be property=value", result.output)

    def test_invalid_protobuf_file_exists(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-p",
                "descriptor=not-afile",
                "-p",
                "value=MyValue",
                "-v",
                "protobuf",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value: File should exist.", result.output)

    def test_invalid_protobuf_file_should_be_a_file(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-p",
                "descriptor=~",
                "-p",
                "value=MyValue",
                "-v",
                "protobuf",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value: Path is a directory.", result.output)

    def test_validate_schema_registry_no_url(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-s",
                "basic.auth.user.info=property",
                "-k",
                "avro",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-s url=my-url'", result.output)

    def test_validate_schema_registry_invalid_config(self):
        result = self.runner.invoke(
            cli,
            [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC, "-s", "not.valid=property"],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value: Valid properties", result.output)

    def test_validate_schema_registry_format(self):
        result = self.runner.invoke(
            cli,
            [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC, "-s", "url=http://my-url"],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-k avro' and/or '-v avro'", result.output)

    def test_validate_schema_registry_invalid_url(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-s",
                "url=no.url",
                "-k",
                "avro",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value: Invalid url.", result.output)

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
            EXPECTED_TOPIC, {BOOTSTRAP_SERVERS: EXPECTED_SERVER}, {}, {}, Format.BYTES, Format.BYTES
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
            {},
            Format.BYTES,
            Format.BYTES,
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeConsumer")
    def test_pass_schema_registry_configs(self, mock_class_kaskade_consumer):
        expected_property_name = "url"
        expected_property_value = "http://my-url"
        expected_property_name2 = "basic.auth.user.info"
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
            {},
            Format.AVRO,
            Format.AVRO,
        )
        self.assertEqual(0, result.exit_code)

    def test_validate_protobuf_format_key(self):
        result = self.runner.invoke(
            cli, [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC, "-k", "protobuf"]
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-p'", result.output)

    def test_validate_protobuf_format_value(self):
        result = self.runner.invoke(
            cli, [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC, "-v", "protobuf"]
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-p'", result.output)

    def test_validate_protobuf_missing_format(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-p",
                f"descriptor={self.temp_descriptor.name}",
                "-p",
                "key=MyMessage",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-k protobuf' and/or '-v protobuf'", result.output)

    def test_validate_protobuf_missing_key(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-p",
                f"descriptor={self.temp_descriptor.name}",
                "-k",
                "protobuf",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-p key=MyMessage'.", result.output)

    def test_validate_protobuf_missing_value(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-p",
                f"descriptor={self.temp_descriptor.name}",
                "-v",
                "protobuf",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-p value=MyMessage'.", result.output)

    def test_validate_protobuf_invalid_option(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-p",
                "descriptor=~/my-file",
                "-p",
                "not=valid",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Valid properties: ['descriptor', 'key', 'value'].", result.output)

    def test_validate_protobuf_descriptor_config(self):
        result = self.runner.invoke(
            cli,
            [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC, "-p", "value=MyMessage"],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-p descriptor=my-descriptor'", result.output)

    def test_validate_protobuf_missing_key_or_value(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-p",
                f"descriptor={self.temp_descriptor.name}",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-k protobuf' and/or '-v protobuf'", result.output)

    @patch("kaskade.main.KaskadeConsumer")
    def test_pass_protobuf_configs(self, mock_class_kaskade_consumer):
        expected_descriptor_name = "descriptor"
        expected_descriptor_value = self.temp_descriptor.name

        expected_value_name = "value"
        expected_value = "my-value"

        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-p",
                f"{expected_descriptor_name}={expected_descriptor_value}",
                "-p",
                f"{expected_value_name}={expected_value}",
                "-v",
                "protobuf",
            ],
        )

        mock_class_kaskade_consumer.assert_called_with(
            EXPECTED_TOPIC,
            {
                BOOTSTRAP_SERVERS: EXPECTED_SERVER,
            },
            {},
            {
                expected_descriptor_name: expected_descriptor_value,
                expected_value_name: expected_value,
            },
            Format.BYTES,
            Format.PROTOBUF,
        )
        self.assertEqual(0, result.exit_code)


if __name__ == "__main__":
    unittest.main()
