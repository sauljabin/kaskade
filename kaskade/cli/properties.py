from click import BadParameter, Context, Parameter


def tuple_properties_to_dict(
    ctx: Context, param: Parameter | None, value: tuple[str, ...]
) -> dict[str, str]:
    if any("=" not in pair for pair in value):
        raise BadParameter(message="Should be property=value.", ctx=ctx, param=param)

    return {key: item for key, _, item in (pair.partition("=") for pair in value)}


def join_bootstrap_servers(
    ctx: Context, param: Parameter | None, value: tuple[str, ...]
) -> str | None:
    """Flatten repeated, comma-separated brokers into one ordered bootstrap.servers value."""
    if not value:
        return None

    servers: list[str] = []
    for raw in value:
        for entry in raw.split(","):
            server = entry.strip()
            if not server:
                raise BadParameter(message=f"Empty broker in {raw!r}.", ctx=ctx, param=param)
            if server in servers:
                raise BadParameter(
                    message=f"Broker {server!r} was specified more than once.",
                    ctx=ctx,
                    param=param,
                )
            servers.append(server)
    return ",".join(servers)
