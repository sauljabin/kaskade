from typing import List

from confluent_kafka.admin import GroupMetadata, PartitionMetadata
from rich.table import Table

from kaskade.renderables.paginated_table import PaginatedTable


class GroupsTable(PaginatedTable):
    def __init__(
        self,
        groups: List[GroupMetadata],
        page_size: int = -1,
        page: int = 1,
        row: int = 0,
    ) -> None:
        self.groups = groups
        super().__init__(len(groups), page_size=page_size, page=page, row=row)

    def renderables(self, start_index: int, end_index: int) -> List[PartitionMetadata]:
        return self.groups[start_index:end_index]

    def render_rows(self, table: Table, renderables: List[GroupMetadata]) -> None:
        for group in renderables:
            table.add_row(
                str(group.id),
                str(group.state),
                str(len(group.members)),
            )

    def render_columns(self, table: Table) -> None:
        table.add_column(
            "id", style="bright_green", header_style="bright_green bold", ratio=60
        )
        table.add_column(
            "state", style="bright_red", header_style="bright_red bold", ratio=20
        )
        table.add_column(
            "members", style="bright_blue", header_style="bright_blue bold", ratio=20
        )
