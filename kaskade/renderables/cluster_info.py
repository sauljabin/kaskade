from rich.table import Table

from kaskade.kafka.models import Cluster


class ClusterInfo:
    def __init__(self, cluster: Cluster) -> None:
        self.cluster = cluster

    def __str__(self) -> str:
        return str(self.cluster)

    def __rich__(self) -> Table:
        table = Table(box=None, expand=False)
        table.add_column(style="bold blue")
        table.add_column()

        table.add_row("kafka:", self.cluster.version)
        table.add_row("brokers:", str(self.cluster.brokers_count()))
        table.add_row("schemas:", "yes" if self.cluster.has_schemas else "no")
        table.add_row(
            "protocol:",
            self.cluster.protocol.lower()
            if self.cluster.protocol is not None
            else "plain",
        )

        return table
