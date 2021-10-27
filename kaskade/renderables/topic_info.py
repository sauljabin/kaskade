from rich.console import Group
from rich.table import Table

from kaskade.kafka.models import Topic
from kaskade.unicodes import APPROXIMATION


class TopicInfo:
    def __init__(self, topic: Topic) -> None:
        self.topic = topic

    def __str__(self) -> str:
        return str(self.topic)

    def __rich__(self) -> Group:
        table = Table(box=None, expand=False, show_header=False, show_edge=False)
        table.add_column(style="bright_magenta bold")
        table.add_column(style="yellow bold")
        table.add_column(style="bright_magenta bold")
        table.add_column(style="yellow bold")
        table.add_column(style="bright_magenta bold")
        table.add_column(style="yellow bold")

        table.add_row(
            "partitions:",
            str(self.topic.partitions_count()),
            "groups:",
            str(self.topic.groups_count()),
            "lag:",
            "{}{}".format(APPROXIMATION, self.topic.lag_count()),
        )
        table.add_row(
            "replicas:",
            str(self.topic.replicas_count()),
            "in sync:",
            str(self.topic.isrs_count()),
        )

        return Group(
            " [bright_magenta bold]name:[/] [yellow bold]{}[/]".format(self.topic.name),
            table,
        )
