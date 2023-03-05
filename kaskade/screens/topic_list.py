import asyncio
from typing import Any, List

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input

from kaskade import logger
from kaskade.kafka.models import Cluster, Topic
from kaskade.styles.unicodes import APPROXIMATION
from kaskade.widgets.header import Header


class TopicList(Screen):
    cluster: Cluster = Cluster()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input()
        yield Container(DataTable())
        yield Footer()

    def on_mount(self) -> None:
        input_filter = self.query_one(Input)
        input_filter.placeholder = "FILTER"
        input_filter.focus()

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
        self.fill_table(table, self.cluster.topics)

    def fill_table(self, table: DataTable[Any], topics: List[Topic]) -> None:
        for topic in topics:
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

    async def on_input_submitted(self, message: Input.Changed) -> None:
        asyncio.create_task(self.filter_topics(message.value))

    async def filter_topics(self, word: str) -> None:
        logger.debug(f"Filtering topics: {word}")
        table = self.query_one(DataTable)
        table.clear()

        if word.strip() == "":
            self.fill_table(table, self.cluster.topics)
        else:
            filtered_topics = [
                topic for topic in self.cluster.topics if word in topic.name
            ]
            self.fill_table(table, filtered_topics)
