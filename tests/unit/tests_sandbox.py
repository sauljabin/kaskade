import unittest
from unittest.mock import MagicMock, patch

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
from sandbox.__main__ import main, sandbox_kafka_config


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
