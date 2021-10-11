from typing import Optional

from rich.console import RenderableType
from rich.table import Table


class KafkaInfo:
    def __init__(
        self,
        kafka_version: Optional[str] = "unknown",
        total_brokers: Optional[int] = 0,
        has_schemas: Optional[bool] = False,
        protocol: Optional[str] = "plain",
    ) -> None:
        self.kafka_info = {
            "kafka": kafka_version.lower(),
            "brokers": str(total_brokers).lower(),
            "schemas": "yes" if has_schemas else "no",
            "protocol": protocol.lower() if protocol is not None else "plain",
        }

    def __str__(self) -> str:
        return str(self.kafka_info)

    def __rich__(self) -> RenderableType:
        table = Table(box=None, expand=False)
        table.add_column(style="bold blue")
        table.add_column()

        for name, value in self.kafka_info.items():
            table.add_row("{}:".format(name), value)

        return table


if __name__ == "__main__":
    from rich.console import Console, RenderableType

    console = Console()
    kafka_info = KafkaInfo(total_brokers=3)
    print(kafka_info)
    console.print(kafka_info)
