from click import BadParameter, Context, Parameter


def tuple_properties_to_dict(
    ctx: Context, param: Parameter | None, value: tuple[str, ...]
) -> dict[str, str]:
    if any("=" not in pair for pair in value):
        raise BadParameter(message="Should be property=value.", ctx=ctx, param=param)

    return {key: item for key, _, item in (pair.partition("=") for pair in value)}
