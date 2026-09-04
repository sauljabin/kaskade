from dataclasses import dataclass
from typing import Any, cast

SECURITY_PROTOCOL = "security.protocol"
SASL_MECHANISM = "sasl.mechanism"
OAUTH_CALLBACK = "oauth_cb"
SASL_SSL = "SASL_SSL"
OAUTHBEARER = "OAUTHBEARER"
AWS_CREDENTIALS_HELP = "Configure AWS credentials or set AWS_PROFILE"


class AwsMskAuthenticationError(ValueError):
    """Raised when Kaskade cannot create an AWS MSK IAM token."""


def generate_aws_msk_auth_token(region: str) -> tuple[str, int]:
    from aws_msk_iam_sasl_signer import MSKAuthTokenProvider  # type: ignore[import-untyped]

    return cast(tuple[str, int], MSKAuthTokenProvider.generate_auth_token(region))


@dataclass(frozen=True)
class AwsMskOAuthCallback:
    region: str

    def __call__(self, _: str) -> tuple[str, float]:
        token, expiration_ms = generate_aws_msk_auth_token(self.region)
        return token, expiration_ms / 1000


def validate_aws_msk_credentials(aws_config: dict[str, str]) -> None:
    if not aws_config:
        return

    try:
        generate_aws_msk_auth_token(aws_config["region"])
    except Exception as ex:
        detail = str(ex).strip().rstrip(".")
        if (
            isinstance(ex, AttributeError)
            and "'NoneType' object has no attribute 'access_key'" in detail
        ):
            detail = "Unable to locate AWS credentials"
        elif not detail:
            detail = ex.__class__.__name__
        raise AwsMskAuthenticationError(
            f"AWS MSK IAM authentication failed: {detail}. {AWS_CREDENTIALS_HELP}."
        ) from ex


def configure_aws_msk_iam(config: dict[str, Any], aws_config: dict[str, str]) -> dict[str, Any]:
    if not aws_config:
        return config

    region = aws_config["region"]
    return config | {
        SECURITY_PROTOCOL: SASL_SSL,
        SASL_MECHANISM: OAUTHBEARER,
        OAUTH_CALLBACK: AwsMskOAuthCallback(region),
    }
