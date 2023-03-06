import asyncio
from typing import Any, List

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input, Label

from kaskade import logger
from kaskade.kafka.models import Cluster, Topic
from kaskade.styles.unicodes import APPROXIMATION
from kaskade.widgets.header import Header


class TopicList(Screen):
    cluster: Cluster = Cluster()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label()
        yield Container(DataTable())
        yield Input()
        yield Footer()

    def on_mount(self) -> None:
        label = self.query_one(Label)
        label.renderable = Text("TOPIC LIST")

        input_filter = self.query_one(Input)
        input_filter.placeholder = "FILTER"
        input_filter.focus()

        header = self.query_one(Header)
        header.cluster = self.cluster

        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.fixed_columns = 1

        table.add_column("NAME")
        table.add_column(Text(str("PARTITIONS"), justify="right"), width=10)
        table.add_column(Text(str("REPLICAS"), justify="right"), width=10)
        table.add_column(Text(str("IN SYNC"), justify="right"), width=10)
        table.add_column(Text(str("GROUPS"), justify="right"), width=10)
        table.add_column(Text(str("RECORDS"), justify="right"), width=10)
        table.add_column(Text(str("LAG"), justify="right"), width=10)
        self.fill_table(table, self.cluster.topics)

    def fill_table(self, table: DataTable[Any], topics: List[Topic]) -> None:
        for topic in topics:
            row = [
                f"[b]{topic.name}[/b]",
                Text(str(topic.partitions_count()), justify="right"),
                Text(str(topic.replicas_count()), justify="right"),
                Text(str(topic.isrs_count()), justify="right"),
                Text(str(topic.groups_count()), justify="right"),
                Text(
                    str(
                        f"{APPROXIMATION}{topic.records_count()}"
                        if topic.records_count() > 0
                        else f"{topic.records_count()}"
                    ),
                    justify="right",
                ),
                Text(
                    str(
                        f"{APPROXIMATION}{topic.lag()}"
                        if topic.lag() > 0
                        else f"{topic.lag()}"
                    ),
                    justify="right",
                ),
            ]
            table.add_row(*row, key=topic.name)

    async def on_input_submitted(self, message: Input.Submitted) -> None:
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
