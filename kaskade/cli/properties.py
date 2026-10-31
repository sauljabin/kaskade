from click import BadParameter, Context, Parameter

from kaskade.configs import PROTOBUF_INCLUDE


def tuple_properties_to_dict(
    ctx: Context, param: Parameter | None, value: tuple[str, ...]
) -> dict[str, str]:
    if any("=" not in pair for pair in value):
        raise BadParameter(message="Should be property=value.", ctx=ctx, param=param)

    return {key: item for key, _, item in (pair.partition("=") for pair in value)}


def protobuf_properties_to_dict(
    ctx: Context, param: Parameter | None, value: tuple[str, ...]
) -> dict[str, str]:
    """Parse properties, flattening repeated, comma-separated include folders in order."""
    config = tuple_properties_to_dict(ctx, param, value)
    pairs = (pair.partition("=") for pair in value)
    includes = [item for key, _, item in pairs if key == PROTOBUF_INCLUDE]
    if includes:
        config[PROTOBUF_INCLUDE] = _join_entries(ctx, param, includes, "include folder")
    return config


def join_bootstrap_servers(
    ctx: Context, param: Parameter | None, value: tuple[str, ...]
) -> str | None:
    """Flatten repeated, comma-separated brokers into one ordered bootstrap.servers value."""
    if not value:
        return None

    return _join_entries(ctx, param, value, "broker")


def _join_entries(
    ctx: Context, param: Parameter | None, values: tuple[str, ...] | list[str], label: str
) -> str:
    entries: list[str] = []
    for raw in values:
        for item in raw.split(","):
            entry = item.strip()
            if not entry:
                raise BadParameter(message=f"Empty {label} in {raw!r}.", ctx=ctx, param=param)
            if entry in entries:
                raise BadParameter(
                    message=f"{label.capitalize()} {entry!r} was specified more than once.",
                    ctx=ctx,
                    param=param,
                )
            entries.append(entry)
    return ",".join(entries)
