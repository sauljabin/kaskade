from typing import List

from rich.table import Table

from kaskade.kafka.models import Partition
from kaskade.renderables.paginated_table import PaginatedTable


class PartitionsTable(PaginatedTable):
    def __init__(
        self,
        partitions: List[Partition],
        page_size: int = -1,
        page: int = 1,
        row: int = 0,
    ) -> None:
        self.partitions = partitions
        super().__init__(len(partitions), page_size=page_size, page=page, row=row)

    def renderables(self, start_index: int, end_index: int) -> List[Partition]:
        return self.partitions[start_index:end_index]

    def render_rows(self, table: Table, renderables: List[Partition]) -> None:
        for partition in renderables:
            table.add_row(
                str(partition.id),
                str(partition.leader),
                str(partition.replicas),
                str(partition.isrs),
            )

    def render_columns(self, table: Table) -> None:
        table.add_column(
            "id",
            style="bright_green",
            header_style="bright_green bold",
            ratio=10,
        )
        table.add_column(
            "leader", style="bright_red", header_style="bright_red bold", ratio=10
        )
        table.add_column(
            "replicas",
            style="bright_blue",
            header_style="bright_blue bold",
            ratio=40,
        )
        table.add_column(
            "in sync",
            style="bright_yellow",
            header_style="bright_yellow bold",
            ratio=40,
        )
