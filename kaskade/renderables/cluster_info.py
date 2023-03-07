from rich.table import Table

from kaskade.kafka.models import Cluster
from kaskade.styles.colors import SECONDARY


class ClusterInfo:
    def __init__(self, cluster: Cluster) -> None:
        self.cluster = cluster

    def __str__(self) -> str:
        return str(self.cluster)

    def __rich__(self) -> Table:
        table = Table(box=None, expand=False)
        table.add_column(style=f"bold {SECONDARY}")
        table.add_column()

        table.add_row("KAFKA:", self.cluster.version)
        table.add_row("BROKERS:", str(self.cluster.brokers_count()))
        table.add_row("TOPICS:", str(self.cluster.topics_count()))
        table.add_row("SCHEMAS:", "yes" if self.cluster.has_schemas else "no")
        table.add_row(
            "PROTOCOL:",
            self.cluster.protocol.lower()
            if self.cluster.protocol is not None
            else "plain",
        )

        return table
