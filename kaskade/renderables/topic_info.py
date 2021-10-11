from rich.table import Table


class TopicInfo:
    def __init__(
        self,
        name: str = "unknown",
        partitions: int = 0,
    ) -> None:
        self.topic_info = {
            "name": name,
            "partitions": str(partitions).lower(),
        }

    def __str__(self) -> str:
        return str(self.topic_info)

    def __rich__(self) -> Table:
        table = Table(box=None, expand=False, show_header=False, show_edge=False)
        table.add_column(style="magenta bold")
        table.add_column(style="yellow bold")

        for name, value in self.topic_info.items():
            table.add_row("{}:".format(name), value)

        return table


if __name__ == "__main__":
    from rich.console import Console

    console = Console()
    topic_info = TopicInfo()
    print(topic_info)
    console.print(topic_info)
