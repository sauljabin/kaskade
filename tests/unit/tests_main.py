import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from kaskade.authentication import (
    OAUTH_CALLBACK,
    OAUTHBEARER,
    SASL_MECHANISM,
    SASL_SSL,
    SECURITY_PROTOCOL,
    AwsMskAuthenticationError,
    AwsMskOAuthCallback,
)
from kaskade.configs import (
    APICURIO,
    APICURIO_OPTION,
    AUTO_OFFSET_RESET,
    BOOTSTRAP_SERVERS,
    EARLIEST,
    REGISTRY_PROVIDERS,
)
from kaskade.deserializers import Deserialization
from kaskade.main import PARTITION_SELECTION_METAVAR, cli
from kaskade.models import PartitionOffset, PartitionSelection
from kaskade.services import PartitionSelectionError
from tests import faker

EXPECTED_TOPIC = "my.topic"
EXPECTED_SERVER = "localhost:9092"
CONFIGURED_SERVER = "configured:9092"


def write_config_ini(
    directory: str,
    kafka: dict[str, str] | None = None,
    registry: dict[str, str] | None = None,
    aws: dict[str, str] | None = None,
) -> str:
    config_path = Path(directory) / "client.ini"
    sections = []
    for section, properties in (("kafka", kafka), ("registry", registry), ("aws", aws)):
        if properties is None:
            continue
        entries = "\n".join(f"{key} = {value}" for key, value in properties.items())
        sections.append(f"[{section}]\n{entries}")
    config_path.write_text("\n\n".join(sections) + "\n")
    return str(config_path)


class TestAdminCli(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.command = "admin"
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        aws_credentials_patcher = patch("kaskade.main.validate_aws_msk_credentials")
        self.mock_validate_aws_msk_credentials = aws_credentials_patcher.start()
        self.addCleanup(aws_credentials_patcher.stop)

    def test_bootstrap_servers_are_required_from_any_source(self):
        result = self.runner.invoke(cli, [self.command])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Bootstrap servers are required", result.output)
        self.assertIn("-b/--bootstrap-servers", result.output)
        self.assertIn("--kafka or --config-file", result.output)

    def test_help_uses_connection_and_application_groups_with_compact_theme(self):
        result = self.runner.invoke(cli, [self.command, "--help"])

        self.assertEqual(0, result.exit_code)
        self.assertIn("Kafka connection options:", result.output)
        self.assertIn("Application options:", result.output)
        self.assertIn("--theme name", result.output)
        self.assertNotIn("--theme [ansi-dark|", result.output)
        examples = [
            line.strip()
            for line in result.output.splitlines()
            if line.strip().startswith("kaskade admin")
        ]
        self.assertEqual(4, len(examples))

    def test_invalid_extra_kafka_config(self):
        result = self.runner.invoke(cli, [self.command, "--kafka", "property.name"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '--kafka': Should be property=value", result.output)

    def test_removed_config_short_option(self):
        result = self.runner.invoke(
            cli, [self.command, "-c", f"{BOOTSTRAP_SERVERS}={CONFIGURED_SERVER}"]
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("No such option '-c'", result.output)

    def test_removed_config_option(self):
        result = self.runner.invoke(
            cli, [self.command, "--config", f"{BOOTSTRAP_SERVERS}={CONFIGURED_SERVER}"]
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("No such option '--config'", result.output)

    def test_invalid_aws_config(self):
        result = self.runner.invoke(cli, [self.command, "--aws", "region"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '--aws': Should be property=value", result.output)

    def test_rejects_unknown_aws_config(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "--aws",
                "profile=example",
                "--aws",
                "region=us-east-1",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value: Valid properties: ['region']", result.output)

    def test_requires_aws_region_value(self):
        result = self.runner.invoke(
            cli,
            [self.command, "-b", EXPECTED_SERVER, "--aws", "region="],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '--aws region=my-region'", result.output)

    @patch("kaskade.main.KaskadeAdmin")
    def test_update_kafka_config(self, mock_class_kaskade_admin):
        result = self.runner.invoke(cli, [self.command, "-b", EXPECTED_SERVER])

        mock_class_kaskade_admin.assert_called_with(
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER}, refresh_interval=None
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeAdmin")
    def test_kafka_config_file(self, mock_class_kaskade_admin):
        config_path = write_config_ini(self.temp_directory.name, kafka={"security.protocol": "SSL"})
        result = self.runner.invoke(
            cli, [self.command, "-b", EXPECTED_SERVER, "--config-file", config_path]
        )

        mock_class_kaskade_admin.assert_called_with(
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER, "security.protocol": "SSL"},
            refresh_interval=None,
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeAdmin")
    def test_infers_bootstrap_servers_from_config_file(self, mock_class_kaskade_admin):
        config_path = write_config_ini(
            self.temp_directory.name,
            {BOOTSTRAP_SERVERS: CONFIGURED_SERVER, "security.protocol": "SSL"},
        )

        result = self.runner.invoke(cli, [self.command, "--config-file", config_path])

        mock_class_kaskade_admin.assert_called_with(
            {BOOTSTRAP_SERVERS: CONFIGURED_SERVER, "security.protocol": "SSL"},
            refresh_interval=None,
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeAdmin")
    def test_config_file_allows_registry_only_section(self, mock_class_kaskade_admin):
        config_path = write_config_ini(
            self.temp_directory.name,
            registry={"url": "https://registry.example.com"},
        )

        result = self.runner.invoke(
            cli,
            [self.command, "-b", EXPECTED_SERVER, "--config-file", config_path],
        )

        mock_class_kaskade_admin.assert_called_with(
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER}, refresh_interval=None
        )
        self.assertEqual(0, result.exit_code)

    def test_config_file_rejects_unknown_section(self):
        config_path = Path(self.temp_directory.name) / "unknown.ini"
        config_path.write_text("[unknown]\nvalue = example\n")

        result = self.runner.invoke(
            cli,
            [self.command, "-b", EXPECTED_SERVER, "--config-file", str(config_path)],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Unknown configuration sections: unknown", result.output)

    @patch("kaskade.main.KaskadeAdmin")
    def test_config_file_preserves_literal_percent(self, mock_class_kaskade_admin):
        config_path = write_config_ini(
            self.temp_directory.name,
            {BOOTSTRAP_SERVERS: CONFIGURED_SERVER, "sasl.password": "secret%value"},
        )

        result = self.runner.invoke(cli, [self.command, "--config-file", config_path])

        mock_class_kaskade_admin.assert_called_with(
            {BOOTSTRAP_SERVERS: CONFIGURED_SERVER, "sasl.password": "secret%value"},
            refresh_interval=None,
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeAdmin")
    def test_infers_bootstrap_servers_from_inline_config(self, mock_class_kaskade_admin):
        result = self.runner.invoke(
            cli,
            [self.command, "--kafka", f"{BOOTSTRAP_SERVERS}={CONFIGURED_SERVER}"],
        )

        mock_class_kaskade_admin.assert_called_with(
            {BOOTSTRAP_SERVERS: CONFIGURED_SERVER}, refresh_interval=None
        )
        self.assertEqual(0, result.exit_code)

    def test_rejects_empty_configured_bootstrap_servers(self):
        result = self.runner.invoke(
            cli,
            [self.command, "--kafka", f"{BOOTSTRAP_SERVERS}="],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Bootstrap servers are required", result.output)

    @patch("kaskade.main.KaskadeAdmin")
    def test_kafka_config_file_overlap(self, mock_class_kaskade_admin):
        config_path = write_config_ini(self.temp_directory.name, kafka={"security.protocol": "SSL"})
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "--kafka",
                "security.protocol=SASL_SSL",
                "--config-file",
                config_path,
            ],
        )

        mock_class_kaskade_admin.assert_called_with(
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER, "security.protocol": "SASL_SSL"},
            refresh_interval=None,
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeAdmin")
    def test_explicit_bootstrap_servers_override_kafka_configuration(
        self, mock_class_kaskade_admin
    ):
        config_path = write_config_ini(
            self.temp_directory.name,
            {BOOTSTRAP_SERVERS: "file:9092", "security.protocol": "SSL"},
        )

        result = self.runner.invoke(
            cli,
            [
                self.command,
                "--config-file",
                config_path,
                "--kafka",
                f"{BOOTSTRAP_SERVERS}=inline:9092",
                "--kafka",
                "security.protocol=SASL_SSL",
                "-b",
                EXPECTED_SERVER,
            ],
        )

        mock_class_kaskade_admin.assert_called_with(
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER, "security.protocol": "SASL_SSL"},
            refresh_interval=None,
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeAdmin")
    def test_inline_bootstrap_servers_override_config_file(self, mock_class_kaskade_admin):
        config_path = write_config_ini(
            self.temp_directory.name,
            {BOOTSTRAP_SERVERS: "file:9092", "security.protocol": "SSL"},
        )

        result = self.runner.invoke(
            cli,
            [
                self.command,
                "--config-file",
                config_path,
                "--kafka",
                f"{BOOTSTRAP_SERVERS}={CONFIGURED_SERVER}",
            ],
        )

        mock_class_kaskade_admin.assert_called_with(
            {BOOTSTRAP_SERVERS: CONFIGURED_SERVER, "security.protocol": "SSL"},
            refresh_interval=None,
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeAdmin")
    def test_uses_application_theme_when_option_is_omitted(self, mock_class_kaskade_admin):
        result = self.runner.invoke(cli, [self.command, "-b", EXPECTED_SERVER])

        self.assertNotIn("theme", vars(mock_class_kaskade_admin.return_value))
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeAdmin")
    def test_pass_theme(self, mock_class_kaskade_admin):
        result = self.runner.invoke(
            cli, [self.command, "-b", EXPECTED_SERVER, "--theme", "dracula"]
        )

        self.assertEqual("dracula", mock_class_kaskade_admin.return_value.theme)
        self.assertEqual(0, result.exit_code)

    def test_invalid_theme(self):
        result = self.runner.invoke(
            cli, [self.command, "-b", EXPECTED_SERVER, "--theme", "invalid"]
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '--theme'", result.output)

    @patch("kaskade.main.KaskadeAdmin")
    def test_pass_refresh_interval(self, mock_class_kaskade_admin):
        result = self.runner.invoke(
            cli,
            [self.command, "-b", EXPECTED_SERVER, "--refresh-interval", "10"],
        )

        mock_class_kaskade_admin.assert_called_with(
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER}, refresh_interval=10
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeAdmin")
    def test_disable_refresh_interval(self, mock_class_kaskade_admin):
        result = self.runner.invoke(
            cli,
            [self.command, "-b", EXPECTED_SERVER, "--refresh-interval", "0"],
        )

        mock_class_kaskade_admin.assert_called_with(
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER}, refresh_interval=0
        )
        self.assertEqual(0, result.exit_code)

    def test_reject_refresh_interval_below_minimum(self):
        result = self.runner.invoke(
            cli,
            [self.command, "-b", EXPECTED_SERVER, "--refresh-interval", "4"],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Should be 0 or at least 5 seconds", result.output)

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
                "--kafka",
                f"{expected_property_name}={expected_property_value}",
            ],
        )

        mock_class_kaskade_admin.assert_called_with(
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER, expected_property_name: expected_property_value},
            refresh_interval=None,
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
                "--kafka",
                f"{expected_property_name}={expected_property_value}",
                "--kafka",
                f"{expected_property_name2}={expected_property_value2}",
            ],
        )

        mock_class_kaskade_admin.assert_called_with(
            {
                BOOTSTRAP_SERVERS: EXPECTED_SERVER,
                expected_property_name: expected_property_value,
                expected_property_name2: expected_property_value2,
            },
            refresh_interval=None,
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeAdmin")
    def test_configures_aws_msk_iam_authentication(self, mock_class_kaskade_admin):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "--kafka",
                f"{SECURITY_PROTOCOL}=PLAINTEXT",
                "--aws",
                "region=us-east-1",
            ],
        )

        config = mock_class_kaskade_admin.call_args.args[0]
        self.assertEqual(SASL_SSL, config[SECURITY_PROTOCOL])
        self.assertEqual(OAUTHBEARER, config[SASL_MECHANISM])
        self.assertEqual(AwsMskOAuthCallback("us-east-1"), config[OAUTH_CALLBACK])
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeAdmin")
    def test_configures_aws_msk_iam_from_config_file(self, mock_class_kaskade_admin):
        config_path = write_config_ini(
            self.temp_directory.name,
            kafka={BOOTSTRAP_SERVERS: EXPECTED_SERVER},
            aws={"region": "us-east-1"},
        )

        result = self.runner.invoke(cli, [self.command, "--config-file", config_path])

        config = mock_class_kaskade_admin.call_args.args[0]
        self.assertEqual(SASL_SSL, config[SECURITY_PROTOCOL])
        self.assertEqual(OAUTHBEARER, config[SASL_MECHANISM])
        self.assertEqual(AwsMskOAuthCallback("us-east-1"), config[OAUTH_CALLBACK])
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeAdmin")
    def test_inline_aws_config_overrides_config_file(self, mock_class_kaskade_admin):
        config_path = write_config_ini(
            self.temp_directory.name,
            kafka={BOOTSTRAP_SERVERS: EXPECTED_SERVER},
            aws={"region": "us-east-1"},
        )

        result = self.runner.invoke(
            cli,
            [
                self.command,
                "--config-file",
                config_path,
                "--aws",
                "region=us-west-2",
            ],
        )

        config = mock_class_kaskade_admin.call_args.args[0]
        self.assertEqual(AwsMskOAuthCallback("us-west-2"), config[OAUTH_CALLBACK])
        self.assertEqual(0, result.exit_code)


class TestConsumerCli(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.command = "consumer"
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        aws_credentials_patcher = patch("kaskade.main.validate_aws_msk_credentials")
        self.mock_validate_aws_msk_credentials = aws_credentials_patcher.start()
        self.addCleanup(aws_credentials_patcher.stop)
        self.temp_descriptor_path = Path(self.temp_directory.name) / "descriptor"
        self.temp_descriptor_path.touch()
        self.temp_avro_path = Path(self.temp_directory.name) / "schema.avsc"
        self.temp_avro_path.touch()

    def test_bootstrap_servers_are_required_from_any_source(self):
        result = self.runner.invoke(cli, [self.command, "-t", EXPECTED_TOPIC])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Bootstrap servers are required", result.output)
        self.assertIn("-b/--bootstrap-servers", result.output)
        self.assertIn("--kafka or --config-file", result.output)

    def test_topic_required(self):
        result = self.runner.invoke(cli, [self.command, "-b", EXPECTED_SERVER])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-t'", result.output)

    @patch("kaskade.main.KaskadeConsumer")
    def test_reports_aws_authentication_failure_before_creating_consumer(
        self, mock_class_kaskade_consumer
    ):
        self.mock_validate_aws_msk_credentials.side_effect = AwsMskAuthenticationError(
            "AWS MSK IAM authentication failed: profile missing. Set AWS_PROFILE."
        )

        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--aws",
                "region=us-east-2",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("AWS MSK IAM authentication failed: profile missing", result.output)
        mock_class_kaskade_consumer.assert_not_called()

    def test_partition_help_documents_selection_format(self):
        result = self.runner.invoke(cli, [self.command, "--help"])

        self.assertEqual(0, result.exit_code)
        self.assertIn(f"--partition {PARTITION_SELECTION_METAVAR}", result.output)

    def test_help_separates_consumer_option_groups_and_documents_constraint(self):
        result = self.runner.invoke(cli, [self.command, "--help"])

        self.assertEqual(0, result.exit_code)
        connection_help = result.output.split("Kafka connection options:", 1)[1].split(
            "AWS options:", 1
        )[0]
        consumption_help = result.output.split("Consumption options:", 1)[1].split(
            "Deserialization options:", 1
        )[0]
        deserialization_help = result.output.split("Deserialization options:", 1)[1].split(
            "Avro options:", 1
        )[0]
        self.assertNotIn("--earliest", connection_help)
        self.assertIn("--earliest", consumption_help)
        self.assertIn("--partition", consumption_help)
        self.assertIn("-k, --key", deserialization_help)
        self.assertNotIn("-k, --kafka", connection_help)
        self.assertIn("--kafka", connection_help)
        self.assertIn("-v, --value", deserialization_help)
        self.assertIn("Key deserializer (case-insensitive)", deserialization_help)
        self.assertIn("Value deserializer (case-insensitive)", deserialization_help)
        self.assertIn("Bytes options:", result.output)
        self.assertIn("--bytes property=value", result.output)
        self.assertIn("Fallback options:", result.output)
        self.assertIn("--fallback property=value", result.output)
        examples = [
            line.strip()
            for line in result.output.splitlines()
            if line.strip().startswith("kaskade consumer")
        ]
        self.assertEqual(4, len(examples))
        self.assertIn("JSON options:", result.output)
        self.assertIn("--json property=value", result.output)
        self.assertIn("Constraints:", result.output)
        self.assertIn("mutually exclusive", result.output)
        self.assertIn("--theme name", result.output)
        self.assertNotIn("--theme [ansi-dark|", result.output)

    @patch("kaskade.main.KaskadeConsumer")
    def test_earliest_configures_all_partition_offset_reset(self, mock_class_kaskade_consumer):
        result = self.runner.invoke(
            cli,
            [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC, "--earliest"],
        )

        self.assertEqual(
            EARLIEST,
            mock_class_kaskade_consumer.call_args.args[1][AUTO_OFFSET_RESET],
        )
        self.assertEqual(0, result.exit_code)

    def test_from_beginning_is_no_longer_supported(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--from-beginning",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("No such option '--from-beginning'", result.output)

    @patch("kaskade.main.KaskadeConsumer")
    def test_parses_repeatable_partition_selections(self, mock_class_kaskade_consumer):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--partition",
                "1:10",
                "--partition",
                "2:earliest",
                "--partition",
                "3",
                "--partition",
                "4:0",
            ],
        )

        self.assertEqual(
            (
                PartitionSelection(1, 10),
                PartitionSelection(2, PartitionOffset.EARLIEST),
                PartitionSelection(3),
                PartitionSelection(4, 0),
            ),
            mock_class_kaskade_consumer.call_args.kwargs["partitions"],
        )
        self.assertEqual(0, result.exit_code)

    def test_rejects_malformed_negative_and_duplicate_partitions(self):
        invalid_values = ("-1", "1:-1", "1:", "1:latest", "1:2:3")
        for value in invalid_values:
            with self.subTest(value=value):
                result = self.runner.invoke(
                    cli,
                    [
                        self.command,
                        "-b",
                        EXPECTED_SERVER,
                        "-t",
                        EXPECTED_TOPIC,
                        "--partition",
                        value,
                    ],
                )
                self.assertGreater(result.exit_code, 0)
                self.assertIn("non-negative numbers", result.output)

        duplicate_result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--partition",
                "1",
                "--partition",
                "1:10",
            ],
        )
        self.assertGreater(duplicate_result.exit_code, 0)
        self.assertIn("Partition 1 was specified more than once", duplicate_result.output)

    def test_rejects_earliest_with_explicit_partitions(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--earliest",
                "--partition",
                "1",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("mutually exclusive", result.output)
        self.assertIn("--earliest", result.output)
        self.assertIn("--partition", result.output)

    @patch("kaskade.main.KaskadeConsumer")
    def test_reports_partition_metadata_validation_before_running_tui(
        self, mock_class_kaskade_consumer
    ):
        mock_class_kaskade_consumer.side_effect = PartitionSelectionError(
            "Partition 9 does not exist in topic 'my.topic'"
        )

        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--partition",
                "9",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '--partition'", result.output)
        self.assertIn("Partition 9 does not exist", result.output)

    def test_invalid_extra_kafka_config(self):
        result = self.runner.invoke(cli, [self.command, "--kafka", "property.name"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '--kafka': Should be property=value", result.output)

    def test_invalid_schema_registry_config(self):
        result = self.runner.invoke(cli, [self.command, "--registry", "property.name"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '--registry': Should be property=value", result.output)

    def test_registry_deserializer_requires_inline_or_file_config(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-v",
                "registry",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Use --registry or the [registry] section in --config-file", result.output)

    def test_invalid_protobuf_config(self):
        result = self.runner.invoke(cli, [self.command, "--protobuf", "property.name"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '--protobuf': Should be property=value", result.output)

    def test_invalid_bytes_config(self):
        result = self.runner.invoke(cli, [self.command, "--bytes", "encoding"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '--bytes': Should be property=value", result.output)

    def test_invalid_fallback_config(self):
        result = self.runner.invoke(cli, [self.command, "--fallback", "encoding"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '--fallback': Should be property=value", result.output)

    def test_invalid_json_config(self):
        result = self.runner.invoke(cli, [self.command, "--json", "framing"])

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Invalid value for '--json': Should be property=value", result.output)

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

    def test_schema_registry_client_validates_missing_url(self):
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
        self.assertIn("Missing required configuration property url", result.output)

    def test_schema_registry_client_validates_unknown_property(self):
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
                "--registry",
                "not.valid=property",
                "-v",
                "registry",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Unrecognized properties: not.valid", result.output)

    @patch("kaskade.main.KaskadeConsumer")
    def test_native_apicurio_provider_uses_official_properties(self, mock_class_kaskade_consumer):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--registry",
                "provider=APICURIO",
                "--registry",
                "apicurio.registry.url=http://registry/apis/registry/v3",
                "--registry",
                "apicurio.registry.use-id=globalId",
                "-v",
                "registry",
            ],
        )

        self.assertEqual(0, result.exit_code, result.output)
        registry_config = mock_class_kaskade_consumer.call_args.args[2]
        self.assertEqual(APICURIO_OPTION, registry_config["provider"])
        self.assertEqual(
            "http://registry/apis/registry/v3",
            registry_config["apicurio.registry.url"],
        )

    def test_native_apicurio_rejects_serializer_only_properties(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--registry",
                "provider=apicurio",
                "--registry",
                "apicurio.registry.url=http://registry/apis/registry/v3",
                "--registry",
                "apicurio.registry.artifact.artifact-id=orders-value",
                "-v",
                "registry",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Unrecognized Apicurio properties", result.output)

    def test_native_apicurio_rejects_generic_aliases(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--registry",
                f"provider={APICURIO}",
                "--registry",
                "url=http://registry",
                "-v",
                "registry",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Unrecognized Apicurio properties: url", result.output)

    def test_apicurio_properties_do_not_infer_provider(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--registry",
                "apicurio.registry.url=http://registry/apis/registry/v3",
                "-v",
                "registry",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn(f"require provider={APICURIO_OPTION}", result.output)

    def test_rejects_unknown_registry_provider(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--registry",
                "provider=OTHER",
                "-v",
                "registry",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn(f"one of {REGISTRY_PROVIDERS}", result.output)

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

    def test_schema_registry_client_validates_invalid_url(self):
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
        self.assertIn("Invalid url no.url", result.output)

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
    def test_client_config_file(self, mock_class_kaskade_consumer):
        config_path = write_config_ini(
            self.temp_directory.name,
            kafka={"security.protocol": "SSL"},
            registry={
                "url": "http://my-url",
                "bearer.auth.credentials.source": "OAUTHBEARER",
            },
        )
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--config-file",
                config_path,
                "-v",
                "registry",
            ],
        )

        mock_class_kaskade_consumer.assert_called_with(
            EXPECTED_TOPIC,
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER, "security.protocol": "SSL"},
            {
                "url": "http://my-url",
                "bearer.auth.credentials.source": "OAUTHBEARER",
            },
            {},
            {},
            Deserialization.BYTES,
            Deserialization.REGISTRY,
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeConsumer")
    def test_inline_registry_config_overrides_config_file(self, mock_class_kaskade_consumer):
        config_path = write_config_ini(
            self.temp_directory.name,
            registry={
                "url": "http://file-url",
                "bearer.auth.credentials.source": "OAUTHBEARER",
            },
        )

        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--config-file",
                config_path,
                "--registry",
                "url=http://inline-url",
                "-v",
                "registry",
            ],
        )

        mock_class_kaskade_consumer.assert_called_with(
            EXPECTED_TOPIC,
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER},
            {
                "url": "http://inline-url",
                "bearer.auth.credentials.source": "OAUTHBEARER",
            },
            {},
            {},
            Deserialization.BYTES,
            Deserialization.REGISTRY,
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeConsumer")
    def test_infers_bootstrap_servers_from_config_file(self, mock_class_kaskade_consumer):
        config_path = write_config_ini(
            self.temp_directory.name,
            {BOOTSTRAP_SERVERS: CONFIGURED_SERVER, "security.protocol": "SSL"},
        )

        result = self.runner.invoke(
            cli,
            [self.command, "-t", EXPECTED_TOPIC, "--config-file", config_path],
        )

        mock_class_kaskade_consumer.assert_called_with(
            EXPECTED_TOPIC,
            {BOOTSTRAP_SERVERS: CONFIGURED_SERVER, "security.protocol": "SSL"},
            {},
            {},
            {},
            Deserialization.BYTES,
            Deserialization.BYTES,
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeConsumer")
    def test_infers_bootstrap_servers_from_inline_config(self, mock_class_kaskade_consumer):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-t",
                EXPECTED_TOPIC,
                "--kafka",
                f"{BOOTSTRAP_SERVERS}={CONFIGURED_SERVER}",
            ],
        )

        mock_class_kaskade_consumer.assert_called_with(
            EXPECTED_TOPIC,
            {BOOTSTRAP_SERVERS: CONFIGURED_SERVER},
            {},
            {},
            {},
            Deserialization.BYTES,
            Deserialization.BYTES,
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeConsumer")
    def test_kafka_config_file_overlap(self, mock_class_kaskade_consumer):
        config_path = write_config_ini(self.temp_directory.name, kafka={"security.protocol": "SSL"})
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--kafka",
                "security.protocol=SASL_SSL",
                "--config-file",
                config_path,
            ],
        )

        mock_class_kaskade_consumer.assert_called_with(
            EXPECTED_TOPIC,
            {BOOTSTRAP_SERVERS: EXPECTED_SERVER, "security.protocol": "SASL_SSL"},
            {},
            {},
            {},
            Deserialization.BYTES,
            Deserialization.BYTES,
        )
        self.assertEqual(0, result.exit_code)

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
    def test_uses_application_theme_when_option_is_omitted(self, mock_class_kaskade_consumer):
        result = self.runner.invoke(
            cli, [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC]
        )

        self.assertNotIn("theme", vars(mock_class_kaskade_consumer.return_value))
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeConsumer")
    def test_pass_theme(self, mock_class_kaskade_consumer):
        result = self.runner.invoke(
            cli, [self.command, "-b", EXPECTED_SERVER, "-t", EXPECTED_TOPIC, "--theme", "dracula"]
        )

        self.assertEqual("dracula", mock_class_kaskade_consumer.return_value.theme)
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
    def test_key_and_value_formats_are_case_insensitive(self, mock_class_kaskade_consumer):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--key",
                "STRING",
                "--value",
                "BYTES",
            ],
        )

        self.assertEqual(0, result.exit_code, result.output)
        self.assertEqual(
            Deserialization.STRING,
            mock_class_kaskade_consumer.call_args.args[5],
        )
        self.assertEqual(
            Deserialization.BYTES,
            mock_class_kaskade_consumer.call_args.args[6],
        )

    @patch("kaskade.main.KaskadeConsumer")
    def test_passes_normalized_bytes_encodings(self, mock_class_kaskade_consumer):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--bytes",
                "encoding=BASE64",
                "--bytes",
                "key.encoding=HEX",
                "--bytes",
                "value.encoding=BYTE_ARRAY",
            ],
        )

        self.assertEqual(
            {
                "encoding": "base64",
                "key.encoding": "hex",
                "value.encoding": "byte-array",
            },
            mock_class_kaskade_consumer.call_args.kwargs["bytes_config"],
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeConsumer")
    def test_passes_normalized_global_fallback_encoding(self, mock_class_kaskade_consumer):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--fallback",
                "encoding=BYTE_ARRAY",
            ],
        )

        self.assertEqual(
            {"encoding": "byte-array"},
            mock_class_kaskade_consumer.call_args.kwargs["fallback_config"],
        )
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeConsumer")
    def test_passes_scoped_json_framing(self, mock_class_kaskade_consumer):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-k",
                "json",
                "-v",
                "json",
                "--json",
                "framing=CONFLUENT",
                "--json",
                "key.framing=APICURIO",
            ],
        )

        self.assertEqual(
            {"framing": "confluent", "key.framing": "apicurio"},
            mock_class_kaskade_consumer.call_args.kwargs["json_config"],
        )
        self.assertEqual(0, result.exit_code)

    def test_rejects_invalid_bytes_encoding(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--bytes",
                "encoding=utf-8",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn(
            "Bytes encoding should be one of ['base64', 'hex', 'byte-array', 'escaped']",
            result.output,
        )

    def test_rejects_invalid_fallback_encoding(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--fallback",
                "encoding=utf-8",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn(
            "Fallback encoding should be one of ['base64', 'hex', 'byte-array', 'escaped']",
            result.output,
        )

    def test_rejects_scoped_fallback_encoding(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--fallback",
                "key.encoding=hex",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Valid properties: ['encoding']", result.output)

    def test_rejects_bytes_encoding_for_inactive_field(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-k",
                "string",
                "--bytes",
                "key.encoding=hex",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("--bytes key.encoding requires '-k bytes'", result.output)

    def test_rejects_bytes_configuration_without_bytes_deserializer(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-k",
                "string",
                "-v",
                "json",
                "--bytes",
                "encoding=hex",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-k bytes' and/or '-v bytes'", result.output)

    def test_rejects_json_framing_for_inactive_field(self):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "-v",
                "json",
                "--json",
                "key.framing=confluent",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("--json key.framing requires '-k json'", result.output)

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
                "--kafka",
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
                "--kafka",
                f"{expected_property_name}={expected_property_value}",
                "--kafka",
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
    def test_configures_aws_msk_iam_authentication(self, mock_class_kaskade_consumer):
        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--aws",
                "region=us-west-2",
            ],
        )

        config = mock_class_kaskade_consumer.call_args.args[1]
        self.assertEqual(SASL_SSL, config[SECURITY_PROTOCOL])
        self.assertEqual(OAUTHBEARER, config[SASL_MECHANISM])
        self.assertEqual(AwsMskOAuthCallback("us-west-2"), config[OAUTH_CALLBACK])
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeConsumer")
    def test_configures_aws_msk_iam_from_config_file(self, mock_class_kaskade_consumer):
        config_path = write_config_ini(
            self.temp_directory.name,
            aws={"region": "us-west-2"},
        )

        result = self.runner.invoke(
            cli,
            [
                self.command,
                "-b",
                EXPECTED_SERVER,
                "-t",
                EXPECTED_TOPIC,
                "--config-file",
                config_path,
            ],
        )

        config = mock_class_kaskade_consumer.call_args.args[1]
        self.assertEqual(SASL_SSL, config[SECURITY_PROTOCOL])
        self.assertEqual(OAUTHBEARER, config[SASL_MECHANISM])
        self.assertEqual(AwsMskOAuthCallback("us-west-2"), config[OAUTH_CALLBACK])
        self.assertEqual(0, result.exit_code)

    @patch("kaskade.main.KaskadeConsumer")
    def test_pass_schema_registry_configs(self, mock_class_kaskade_consumer):
        expected_property_name = "url"
        expected_property_value = "http://my-url"
        expected_property_name2 = "bearer.auth.credentials.source"
        expected_property_value2 = "OAUTHBEARER"
        expected_property_name3 = "bearer.auth.client.secret"
        expected_property_value3 = "property.value3="

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
                "--registry",
                f"{expected_property_name3}={expected_property_value3}",
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
                expected_property_name3: expected_property_value3,
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
                f"descriptor={self.temp_descriptor_path}",
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
                f"descriptor={self.temp_descriptor_path}",
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
                f"descriptor={self.temp_descriptor_path}",
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
        self.assertIn(
            "Valid properties: ['descriptor', 'key', 'value', 'framing', "
            "'key.framing', 'value.framing'].",
            result.output,
        )

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
        self.assertIn(
            "Valid properties: ['key', 'value', 'framing', 'key.framing', " "'value.framing'].",
            result.output,
        )

    def test_validate_avro_invalid_framing(self):
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
                f"value={self.temp_avro_path}",
                "--avro",
                "framing=automatic",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn(
            "Avro framing should be one of ['raw', 'apicurio', 'confluent']",
            result.output,
        )

    @patch("kaskade.main.KaskadeConsumer")
    def test_passes_scoped_avro_framing(self, mock_class_kaskade_consumer):
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
                "-v",
                "avro",
                "--avro",
                f"key={self.temp_avro_path}",
                "--avro",
                f"value={self.temp_avro_path}",
                "--avro",
                "framing=CONFLUENT",
                "--avro",
                "key.framing=RAW",
            ],
        )

        self.assertEqual(
            {
                "key": str(self.temp_avro_path),
                "value": str(self.temp_avro_path),
                "framing": "confluent",
                "key.framing": "raw",
            },
            mock_class_kaskade_consumer.call_args.args[4],
        )
        self.assertEqual(0, result.exit_code)

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
                f"descriptor={self.temp_descriptor_path}",
            ],
        )

        self.assertGreater(result.exit_code, 0)
        self.assertIn("Missing option '-k protobuf' and/or '-v protobuf'", result.output)

    @patch("kaskade.main.KaskadeConsumer")
    def test_pass_protobuf_configs(self, mock_class_kaskade_consumer):
        expected_descriptor_name = "descriptor"
        expected_descriptor_value = str(self.temp_descriptor_path)

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
                "--protobuf",
                "value.framing=CONFLUENT",
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
                "value.framing": "confluent",
            },
            {},
            Deserialization.BYTES,
            Deserialization.PROTOBUF,
        )
        self.assertEqual(0, result.exit_code)


if __name__ == "__main__":
    unittest.main()
