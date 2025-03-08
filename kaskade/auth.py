from typing import Any, Callable

from aws_msk_iam_sasl_signer import MSKAuthTokenProvider

from kaskade.configs import DEFAULT_AWS_IAM_REGION

def construct_oauth_callback(region: str) -> Callable:
    def oauth_cb(oauth_config):
        auth_token, expiry_ms = MSKAuthTokenProvider.generate_auth_token(region)
        # Note that this library expects oauth_cb to return expiry time in seconds since epoch, while the token generator returns expiry in ms
        return auth_token, expiry_ms/1000
    return oauth_cb

def uses_oauthbearer_sasl_mechanism(config: dict[str, Any]) -> bool:
    return "sasl.mechanism" in config and config["sasl.mechanism"] == "OAUTHBEARER"

def get_additional_auth_config(config: dict[str, Any]) -> dict[str, Callable]:
    """
    To enable AWS IAM support, we need to register an oauth callback function in the confluent-kafka configuration
    """
    aws_region = config.get("aws.region", DEFAULT_AWS_IAM_REGION)
    return {"oauth_cb": construct_oauth_callback(aws_region)} if uses_oauthbearer_sasl_mechanism(config) else {}
