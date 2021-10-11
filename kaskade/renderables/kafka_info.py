from rich.table import Table


class KafkaInfo:
    def __init__(
        self,
        kafka_version: str = "unknown",
        total_brokers: int = 0,
        has_schemas: bool = False,
        protocol: str = "plain",
    ) -> None:
        self.kafka_info = {
            "kafka": kafka_version.lower(),
            "brokers": str(total_brokers).lower(),
            "schemas": "yes" if has_schemas else "no",
            "protocol": protocol.lower() if protocol is not None else "plain",
        }

    def __str__(self) -> str:
        return str(self.kafka_info)

    def __rich__(self) -> Table:
        table = Table(box=None, expand=False)
        table.add_column(style="bold blue")
        table.add_column()

        for name, value in self.kafka_info.items():
            table.add_row("{}:".format(name), value)

        return table
