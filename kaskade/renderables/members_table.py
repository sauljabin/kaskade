from typing import List

from rich.table import Table

from kaskade.kafka.models import GroupMember
from kaskade.renderables.paginated_table import PaginatedTable


class MembersTable(PaginatedTable):
    def __init__(
        self,
        group_members: List[GroupMember],
        page_size: int = -1,
        page: int = 1,
        row: int = 0,
    ) -> None:
        self.group_members = group_members
        super().__init__(len(group_members), page_size=page_size, page=page, row=row)

    def renderables(self, start_index: int, end_index: int) -> List[GroupMember]:
        return self.group_members[start_index:end_index]

    def render_rows(self, table: Table, renderables: List[GroupMember]) -> None:
        for group_member in renderables:
            table.add_row(
                str(group_member.group),
                str(group_member.id),
                str(group_member.client_id),
                str(group_member.client_host),
            )

    def render_columns(self, table: Table) -> None:
        header_style = "bright_magenta bold"
        table.add_column("group", header_style=header_style, ratio=35, no_wrap=True)
        table.add_column("id", header_style=header_style, ratio=35, no_wrap=True)
        table.add_column("client id", header_style=header_style, ratio=15, no_wrap=True)
        table.add_column(
            "client host", header_style=header_style, ratio=15, no_wrap=True
        )
