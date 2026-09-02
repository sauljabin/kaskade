import unittest
from functools import partial
from unittest.mock import MagicMock, call, patch

import click
from click.testing import CliRunner

from kaskade.authentication import (
    OAUTH_CALLBACK,
    OAUTHBEARER,
    SASL_MECHANISM,
    SASL_SSL,
    SECURITY_PROTOCOL,
    AwsMskOAuthCallback,
)
from kaskade.configs import BOOTSTRAP_SERVERS
from sandbox.__main__ import (
    AVAILABLE_TOPICS,
    ERRORS_TOPIC,
    INVALID_UTF8_HEADER,
    NULL_HEADER,
    NULL_TOPIC,
    Populator,
    main,
    sandbox_kafka_config,
)


class TestPopulator(unittest.TestCase):
    @patch("sandbox.__main__.Producer")
    @patch("sandbox.__main__.AdminClient")
    def test_errors_topic_includes_invalid_utf8_header(
        self, _: MagicMock, mock_producer: MagicMock
    ) -> None:
        serializer = MagicMock(return_value=b"valid")
        faker = MagicMock()
        faker.name.return_value = "Sandbox User"
        populator = Populator({})

        populator.populate_errors(serializer, faker, 5)

        headers = [
            produced.kwargs["headers"]
            for produced in mock_producer.return_value.produce.call_args_list
        ]
        self.assertEqual(
            [
                [("sandbox-error-case", b"key")],
                [("sandbox-error-case", b"value")],
                [("sandbox-error-case", b"both")],
                [("sandbox-error-case", b"header"), INVALID_UTF8_HEADER],
                [("sandbox-error-case", b"valid")],
            ],
            headers,
        )
        self.assertEqual(b"\xff", INVALID_UTF8_HEADER[1])
        with self.assertRaisesRegex(UnicodeDecodeError, "codec can't decode byte 0xff"):
            INVALID_UTF8_HEADER[1].decode("utf-8")

    @patch("sandbox.__main__.Producer")
    @patch("sandbox.__main__.AdminClient")
    def test_null_topic_contains_null_keys_values_and_header(
        self, _: MagicMock, mock_producer: MagicMock
    ) -> None:
        populator = Populator({})

        populator.populate_null(3)

        self.assertEqual(
            [call(NULL_TOPIC, key=None, value=None, headers=[NULL_HEADER])] * 3,
            mock_producer.return_value.produce.call_args_list,
        )
        mock_producer.return_value.flush.assert_called_once_with(5)

    @patch("sandbox.__main__.Producer")
    @patch("sandbox.__main__.AdminClient")
    def test_create_topic_uses_broker_replication_defaults(
        self, mock_admin_client: MagicMock, _: MagicMock
    ) -> None:
        mock_admin_client.return_value.create_topics.return_value = {"orders": MagicMock()}

        Populator({}).create_topic("orders")

        topic = mock_admin_client.return_value.create_topics.call_args.args[0][0]
        self.assertEqual(10, topic.num_partitions)
        self.assertEqual(-1, topic.replication_factor)
        self.assertEqual({}, topic.config)

    @patch("sandbox.__main__.Producer")
    @patch("sandbox.__main__.AdminClient")
    def test_create_topic_uses_explicit_replication_settings(
        self, mock_admin_client: MagicMock, _: MagicMock
    ) -> None:
        mock_admin_client.return_value.create_topics.return_value = {"orders": MagicMock()}

        Populator({}, partitions=6, replication_factor=3, min_insync_replicas=2).create_topic(
            "orders"
        )

        topic = mock_admin_client.return_value.create_topics.call_args.args[0][0]
        self.assertEqual(6, topic.num_partitions)
        self.assertEqual(3, topic.replication_factor)
        self.assertEqual({"min.insync.replicas": "2"}, topic.config)


class TestSandboxKafkaConfig(unittest.TestCase):
    def test_preserves_local_kafka_config_without_aws_properties(self) -> None:
        config = sandbox_kafka_config("localhost:19092", {})

        self.assertEqual({BOOTSTRAP_SERVERS: "localhost:19092"}, config)

    def test_configures_aws_msk_iam_authentication(self) -> None:
        config = sandbox_kafka_config("broker:9098", {"region": "us-east-1"})

        self.assertEqual("broker:9098", config[BOOTSTRAP_SERVERS])
        self.assertEqual(SASL_SSL, config[SECURITY_PROTOCOL])
        self.assertEqual(OAUTHBEARER, config[SASL_MECHANISM])
        self.assertEqual(AwsMskOAuthCallback("us-east-1"), config[OAUTH_CALLBACK])

    def test_rejects_unknown_aws_config(self) -> None:
        with self.assertRaisesRegex(click.BadParameter, "Valid properties"):
            sandbox_kafka_config("broker:9098", {"profile": "example", "region": "us-east-1"})

    def test_requires_aws_region_value(self) -> None:
        with self.assertRaises(click.MissingParameter) as raised:
            sandbox_kafka_config("broker:9098", {"region": ""})

        self.assertEqual("'--aws region=my-region'", raised.exception.param_hint)

    @patch("sandbox.__main__.run_population")
    @patch("sandbox.__main__.Populator")
    def test_cli_passes_aws_config_to_populator(
        self, mock_populator: MagicMock, _: MagicMock
    ) -> None:
        result = CliRunner().invoke(
            main,
            [
                "--messages",
                "0",
                "--bootstrap-servers",
                "broker:9098",
                "--aws",
                "region=us-west-2",
            ],
        )

        self.assertEqual(0, result.exit_code, result.output)
        config = mock_populator.call_args.args[0]
        self.assertEqual(AwsMskOAuthCallback("us-west-2"), config[OAUTH_CALLBACK])
        self.assertEqual(
            {
                "partitions": 10,
                "replication_factor": None,
                "min_insync_replicas": None,
            },
            mock_populator.call_args.kwargs,
        )

    @patch("sandbox.__main__.run_population")
    @patch("sandbox.__main__.Populator")
    def test_cli_passes_topic_settings_to_populator(
        self, mock_populator: MagicMock, mock_run_population: MagicMock
    ) -> None:
        result = CliRunner().invoke(
            main,
            [
                "--messages",
                "0",
                "--partitions",
                "6",
                "--replication-factor",
                "3",
                "--min-insync-replicas",
                "2",
            ],
        )

        self.assertEqual(0, result.exit_code, result.output)
        self.assertEqual(
            {
                "partitions": 6,
                "replication_factor": 3,
                "min_insync_replicas": 2,
            },
            mock_populator.call_args.kwargs,
        )
        self.assertEqual(14, mock_run_population.call_count)
        self.assertEqual(ERRORS_TOPIC, mock_run_population.call_args.args[3])

        actions = [
            population_call.args[4] for population_call in mock_run_population.call_args_list
        ]
        self.assertTrue(all(isinstance(action, partial) for action in actions))
        self.assertEqual(
            [
                mock_populator.return_value.populate_string,
                mock_populator.return_value.populate_integer,
                mock_populator.return_value.populate_long,
                mock_populator.return_value.populate_float,
                mock_populator.return_value.populate_double,
                mock_populator.return_value.populate_boolean,
                mock_populator.return_value.populate_null,
                mock_populator.return_value.populate_json,
                mock_populator.return_value.populate_json_schema,
                mock_populator.return_value.populate_protobuf,
                mock_populator.return_value.populate_protobuf_schema,
                mock_populator.return_value.populate_avro,
                mock_populator.return_value.populate_avro_schema,
                mock_populator.return_value.populate_errors,
            ],
            [action.func for action in actions],
        )

    @patch("sandbox.__main__.run_population")
    @patch("sandbox.__main__.Populator")
    def test_cli_populates_only_selected_topics(
        self, _: MagicMock, mock_run_population: MagicMock
    ) -> None:
        result = CliRunner().invoke(
            main,
            ["--messages", "0", "--topic", "string", "--topic", ERRORS_TOPIC],
        )

        self.assertEqual(0, result.exit_code, result.output)
        self.assertEqual(
            ["string", ERRORS_TOPIC],
            [call.args[3] for call in mock_run_population.call_args_list],
        )

    def test_cli_rejects_unknown_topic(self) -> None:
        result = CliRunner().invoke(main, ["--topic", "unknown"])

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("Invalid value for '--topic'", result.output)
        self.assertIn(AVAILABLE_TOPICS[0], result.output)

    def test_cli_rejects_duplicate_topic(self) -> None:
        result = CliRunner().invoke(main, ["--topic", "string", "--topic", "string"])

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("Each topic may only be selected once", result.output)
