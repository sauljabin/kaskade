import asyncio
from typing import Any, List

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input

from kaskade.config import Config
from kaskade.kafka.models import Cluster, Topic
from kaskade.styles.unicodes import APPROXIMATION
from kaskade.widgets.header import Header


class TopicList(Screen):
    config: Config | None = None
    cluster = Cluster()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(DataTable())
        yield Input()
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
        table.border_title = "topics"

        table.add_column("name")
        table.add_column(Text("partitions", justify="right"), width=10)
        table.add_column(Text("replicas", justify="right"), width=10)
        table.add_column(Text("in sync", justify="right"), width=10)
        table.add_column(Text("groups", justify="right"), width=10)
        table.add_column(Text("records", justify="right"), width=10)
        table.add_column(Text("lag", justify="right"), width=10)
        asyncio.create_task(self.filter_topics(""))

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
                    str(f"{APPROXIMATION}{topic.lag()}" if topic.lag() > 0 else f"{topic.lag()}"),
                    justify="right",
                ),
            ]
            table.add_row(*row, key=topic.name)

    async def on_input_submitted(self, message: Input.Submitted) -> None:
        asyncio.create_task(self.filter_topics(message.value))

    async def filter_topics(self, word: str) -> None:
        table = self.query_one(DataTable)
        table.clear()

        if self.config and not bool(self.config.kaskade.get("show.internals")):
            filtered_topics = [
                topic
                for topic in self.cluster.topics
                if not topic.name.startswith("_") and word.strip() in topic.name
            ]
        else:
            filtered_topics = [topic for topic in self.cluster.topics if word.strip() in topic.name]
        table.border_title = f"topics ({len(filtered_topics)})"
        self.fill_table(table, filtered_topics)
