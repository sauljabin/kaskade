from click import BadParameter, Context, MissingParameter, Parameter

from kaskade.configs import AWS_CONFIGS


def tuple_properties_to_dict(
    ctx: Context, param: Parameter | None, value: tuple[str, ...]
) -> dict[str, str]:
    if [pair for pair in value if "=" not in pair]:
        raise BadParameter(message="Should be property=value.", ctx=ctx, param=param)

    return {key: item for key, item in [pair.split("=", 1) for pair in value]}


def validate_aws_config(aws_config: dict[str, str]) -> None:
    if not aws_config:
        return

    if [config for config in aws_config if config not in AWS_CONFIGS]:
        raise BadParameter(message=f"Valid properties: {AWS_CONFIGS}.")

    if not aws_config.get("region"):
        raise MissingParameter(param_hint="'--aws region=my-region'", param_type="option")
