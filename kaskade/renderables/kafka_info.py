from rich.table import Table


class KafkaInfo:
    def __init__(
        self,
        kafka_version="unknown",
        total_brokers="unknown",
        has_schemas=False,
        protocol="plain",
    ):
        self.kafka_version = kafka_version
        self.total_brokers = total_brokers
        self.has_schemas = has_schemas
        self.protocol = protocol

    def __rich__(self):
        kafka_info = Table(box=None, expand=False)
        kafka_info.add_column(style="bold blue")
        kafka_info.add_column()

        kafka_info.add_row("kafka:", self.kafka_version.lower())
        kafka_info.add_row("brokers:", str(self.total_brokers).lower())
        kafka_info.add_row("schemas:", "yes" if self.has_schemas else "no")
        kafka_info.add_row(
            "protocol:", self.protocol.lower() if self.protocol else "plain"
        )
        return kafka_info


if __name__ == "__main__":
    from rich.console import Console

    console = Console()
    console.print(KafkaInfo(total_brokers=3))
