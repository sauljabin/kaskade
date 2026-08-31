import unittest
from unittest.mock import MagicMock, patch

from kaskade.authentication import (
    OAUTH_CALLBACK,
    OAUTHBEARER,
    SASL_MECHANISM,
    SASL_SSL,
    SECURITY_PROTOCOL,
    AwsMskOAuthCallback,
    configure_aws_msk_iam,
)


class TestAwsMskAuthentication(unittest.TestCase):
    def test_leaves_config_unchanged_without_region(self) -> None:
        config = {"bootstrap.servers": "localhost:9092"}

        result = configure_aws_msk_iam(config, {})

        self.assertIs(config, result)

    def test_configures_iam_authentication(self) -> None:
        result = configure_aws_msk_iam(
            {
                "bootstrap.servers": "broker:9098",
                SECURITY_PROTOCOL: "PLAINTEXT",
                SASL_MECHANISM: "PLAIN",
            },
            {"region": "us-east-1"},
        )

        self.assertEqual(SASL_SSL, result[SECURITY_PROTOCOL])
        self.assertEqual(OAUTHBEARER, result[SASL_MECHANISM])
        self.assertEqual(AwsMskOAuthCallback("us-east-1"), result[OAUTH_CALLBACK])

    @patch("kaskade.authentication.generate_aws_msk_auth_token")
    def test_callback_converts_expiration_to_seconds(self, mock_generate: MagicMock) -> None:
        mock_generate.return_value = ("token", 1_725_000_000_000)

        token, expiration = AwsMskOAuthCallback("us-west-2")("ignored")

        self.assertEqual("token", token)
        self.assertEqual(1_725_000_000, expiration)
        mock_generate.assert_called_once_with("us-west-2")
