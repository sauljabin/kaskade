from typing import List

from rich.table import Table

from kaskade.kafka.models import Group
from kaskade.renderables.paginated_table import PaginatedTable


class GroupsTable(PaginatedTable):
    def __init__(
        self,
        groups: List[Group],
        page_size: int = -1,
        page: int = 1,
        row: int = 0,
    ) -> None:
        self.groups = groups
        super().__init__(len(groups), page_size=page_size, page=page, row=row)

    def renderables(self, start_index: int, end_index: int) -> List[Group]:
        return self.groups[start_index:end_index]

    def render_rows(self, table: Table, renderables: List[Group]) -> None:
        for group in renderables:
            state = group.state.lower()
            lag = group.lag_count()
            table.add_row(
                str(group.id),
                str(f"[green]{state}[/]" if state == "stable" else f"[red]{state}[/]"),
                str(group.members),
                str(f"[green]{lag}[/]" if lag == 0 else f"[red]{lag}[/]"),
            )

    def render_columns(self, table: Table) -> None:
        table.add_column("id", header_style="bright_magenta bold", ratio=60)
        table.add_column("state", header_style="bright_magenta bold", ratio=20)
        table.add_column("members", header_style="bright_magenta bold", ratio=20)
        table.add_column("lag", header_style="bright_magenta bold", ratio=20)
