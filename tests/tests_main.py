import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from kaskade.configs import BOOTSTRAP_SERVERS
from kaskade.main import cli
from kaskade.deserializers import Deserialization
from tests import faker

EXPECTED_TOPIC = "my.topic"
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
        result = self.runner.invoke(cli, [self.command, "-c", "property.name"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn(
            "Invalid value for '-c' / '--config': Should be property=value", result.output
        )

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
                "-c",
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
                "-c",
                f"{expected_property_name}={expected_property_value}",
                "-c",
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
        result = self.runner.invoke(cli, [self.command, "-c", "property.name"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn(
            "Invalid value for '-c' / '--config': Should be property=value", result.output
        )

    def test_invalid_schema_registry_config(self):
        result = self.runner.invoke(cli, [self.command, "--registry", "property.name"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '--registry': Should be property=value", result.output)

    def test_invalid_protobuf_config(self):
        result = self.runner.invoke(cli, [self.command, "--protobuf", "property.name"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '--protobuf': Should be property=value", result.output)

    def test_invalid_protobuf_file_exists(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--protobuf",
                "descriptor=not-afile",
                "--protobuf",
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
                "--protobuf",
                "descriptor=~",
                "--protobuf",
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
                "--registry",
                "basic.auth.user.info=property",
                "-k",
                "registry",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '--registry url=my-url'", result.output)

    def test_validate_schema_registry_invalid_config(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--registry",
                "not.valid=property",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value: Valid properties", result.output)

    def test_validate_avro_invalid_config(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--avro",
                "not.valid=property",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value: Valid properties", result.output)

    def test_validate_schema_registry_format(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--registry",
                "url=http://my-url",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-k registry' and/or '-v registry'", result.output)

    def test_validate_schema_registry_invalid_url(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--registry",
                "url=no.url",
                "-k",
                "registry",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value: Invalid url.", result.output)

    def test_validate_missing_options_with_avro_key(self):
        result = self.runner.invoke(
            cli, [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC, "-k", "avro"]
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '--avro'", result.output)

    def test_validate_missing_options_with_avro_value(self):
        result = self.runner.invoke(
            cli, [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC, "-v", "avro"]
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '--avro'", result.output)

    @patch("kaskade.main.KaskadeConsumer")
    def test_update_kafka_config(self, mock_class_kaskade_consumer):
        result = self.runner.invoke(
            cli, [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC]
        )

        mock_class_kaskade_consumer.assert_called_with(
            EXPECTED_TOPIC,
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER},
            {},
            {},
            {},
            Deserialization.BYTES,
            Deserialization.BYTES,
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeConsumer")
    def test_pass_right_format(self, mock_class_kaskade_consumer):
        options = ["long", "bytes", "string"]

        expected_key_deserialization = faker.random.choice(options)
        expected_value_deserialization = faker.random.choice(options)

        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-k",
                expected_key_deserialization,
                "-v",
                expected_value_deserialization,
            ],
        )

        mock_class_kaskade_consumer.assert_called_with(
            EXPECTED_TOPIC,
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER},
            {},
            {},
            {},
            Deserialization.from_str(expected_key_deserialization),
            Deserialization.from_str(expected_value_deserialization),
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
                "-c",
                f"{expected_property_name}={expected_property_value}",
            ],
        )

        mock_class_kaskade_consumer.assert_called_with(
            EXPECTED_TOPIC,
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER, expected_property_name: expected_property_value},
            {},
            {},
            {},
            Deserialization.BYTES,
            Deserialization.BYTES,
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
                "-c",
                f"{expected_property_name}={expected_property_value}",
                "-c",
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
            {},
            Deserialization.BYTES,
            Deserialization.BYTES,
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
                "--registry",
                f"{expected_property_name}={expected_property_value}",
                "--registry",
                f"{expected_property_name2}={expected_property_value2}",
                "-k",
                "registry",
                "-v",
                "registry",
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
            {},
            Deserialization.REGISTRY,
            Deserialization.REGISTRY,
        )
        self.assertEqual(0, result.exit_code)

    def test_validate_protobuf_format_key(self):
        result = self.runner.invoke(
            cli, [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC, "-k", "protobuf"]
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '--protobuf'", result.output)

    def test_validate_protobuf_format_value(self):
        result = self.runner.invoke(
            cli, [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC, "-v", "protobuf"]
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '--protobuf'", result.output)

    def test_validate_protobuf_missing_format(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--protobuf",
                f"descriptor={self.temp_descriptor.name}",
                "--protobuf",
                "key=MyMessage",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-k protobuf' and/or '-v protobuf'", result.output)

    def test_validate_avro_missing_format(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--avro",
                "key=my-avro.avsc",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-k avro' and/or '-v avro'", result.output)

    def test_validate_avro_missing_key(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-k",
                "avro",
                "--avro",
                "value=my-value",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '--avro key=my-schema.avsc'.", result.output)

    def test_validate_avro_missing_value(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-v",
                "avro",
                "--avro",
                "key=my-value",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '--avro value=my-schema.avsc'.", result.output)

    def test_validate_protobuf_missing_key(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--protobuf",
                f"descriptor={self.temp_descriptor.name}",
                "-k",
                "protobuf",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '--protobuf key=MyMessage'.", result.output)

    def test_validate_protobuf_missing_value(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--protobuf",
                f"descriptor={self.temp_descriptor.name}",
                "-v",
                "protobuf",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '--protobuf value=MyMessage'.", result.output)

    def test_validate_protobuf_invalid_option(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--protobuf",
                "descriptor=~/my-file",
                "--protobuf",
                "not=valid",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Valid properties: ['descriptor', 'key', 'value'].", result.output)

    def test_validate_avro_invalid_option(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--avro",
                "not=valid",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Valid properties: ['key', 'value'].", result.output)

    def test_validate_protobuf_descriptor_config(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--protobuf",
                "value=MyMessage",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '--protobuf descriptor=my-descriptor'", result.output)

    def test_validate_protobuf_missing_key_or_value(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--protobuf",
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
                "--protobuf",
                f"{expected_descriptor_name}={expected_descriptor_value}",
                "--protobuf",
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
            {},
            Deserialization.BYTES,
            Deserialization.PROTOBUF,
        )
        self.assertEqual(0, result.exit_code)


if __name__ == "__main__":
    unittest.main()
