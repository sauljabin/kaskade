from textual.app import ComposeResult
from textual.containers import Container
from textual.events import Key
from textual.screen import Screen
from textual.widgets import DataTable, Footer

from kaskade import logger
from kaskade.kafka.models import Cluster
from kaskade.styles.unicodes import APPROXIMATION
from kaskade.widgets.header import Header


class TopicList(Screen):
    cluster: Cluster = Cluster()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(DataTable())
        yield Footer()

    def on_mount(self) -> None:
        header = self.query_one(Header)
        header.cluster = self.cluster

        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.fixed_columns = 1

        table.add_column("NAME")
        table.add_column("PARTITIONS", width=10)
        table.add_column("REPLICAS", width=10)
        table.add_column("IN SYNC", width=10)
        table.add_column("GROUPS", width=10)
        table.add_column("RECORDS", width=10)
        table.add_column("LAG", width=10)
        for topic in self.cluster.topics:
            row = [
                f"[b]{topic.name}[/b]",
                topic.partitions_count(),
                topic.replicas_count(),
                topic.isrs_count(),
                topic.groups_count(),
                f"{APPROXIMATION}{topic.records_count()}"
                if topic.records_count() > 0
                else f"{topic.records_count()}",
                f"{APPROXIMATION}{topic.lag()}"
                if topic.lag() > 0
                else f"{topic.lag()}",
            ]
            table.add_row(*row)

    def on_key(self, event: Key) -> None:
        logger.debug("pepe")
