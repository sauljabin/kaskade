from rich.table import Table


class KafkaInfo:
    def __init__(
        self,
        kafka_version="unknown",
        total_brokers="unknown",
        has_schemas=False,
        protocol="plain",
    ):
        self.kafka_info = {
            "kafka": kafka_version.lower(),
            "brokers": str(total_brokers).lower(),
            "schemas": "yes" if has_schemas else "no",
            "protocol": protocol.lower() if protocol else "plain",
        }

    def __str__(self):
        return str(self.kafka_info)

    def __rich__(self):
        table = Table(box=None, expand=False)
        table.add_column(style="bold blue")
        table.add_column()

        for name, value in self.kafka_info.items():
            table.add_row("{}:".format(name), value)

        return table


if __name__ == "__main__":
    from rich.console import Console

    console = Console()
    kafka_info = KafkaInfo(total_brokers=3)
    print(kafka_info)
    console.print(kafka_info)
