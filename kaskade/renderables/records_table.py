from typing import List

from rich.console import Group
from rich.padding import Padding
from rich.style import Style
from rich.table import Table
from rich.text import Text

from kaskade.kafka.models import Record
from kaskade.unicodes import APPROXIMATION


class RecordsTable:
    def __init__(
        self, records: List[Record], total_reads: int, page_size: int, row: int = 0
    ) -> None:
        self.records = records
        self.total_reads = total_reads
        self.page_size = page_size
        self.row = row

    def __rich__(self) -> Group:
        table = Table(
            title_style="",
            expand=True,
            box=None,
            show_edge=False,
        )
        table.add_column(
            "date", header_style="bright_magenta bold", ratio=15, no_wrap=True
        )
        table.add_column(
            "partition", header_style="bright_magenta bold", ratio=7, no_wrap=True
        )
        table.add_column(
            "offset", header_style="bright_magenta bold", ratio=7, no_wrap=True
        )
        table.add_column(
            "headers", header_style="bright_magenta bold", ratio=7, no_wrap=True
        )
        table.add_column(
            "key", header_style="bright_magenta bold", ratio=24, no_wrap=True
        )
        table.add_column(
            "value", header_style="bright_magenta bold", ratio=50, no_wrap=True
        )

        for record in self.records:
            table.add_row(
                str(
                    record.date.strftime("%Y-%d-%m %H:%M:%S")
                    if record.date is not None
                    else None
                ),
                str(record.partition),
                str(record.offset),
                str(record.headers_count()),
                str(record.key).replace("\n", ""),
                str(record.value).replace("\n", ""),
            )

        pagination_info = Text.from_markup(
            "[yellow bold]{}{}[/]".format(APPROXIMATION, self.total_reads),
            justify="right",
        )

        if 0 < self.row <= len(table.rows):
            table.rows[self.row - 1].style = Style(
                bold=True, dim=False, bgcolor="grey35"
            )

        missing_rows = self.page_size - len(table.rows)
        padding = Padding(
            Padding(pagination_info, (0, 1, 0, 0)),
            (missing_rows, 0, 0, 0),
        )

        return Group(table, padding)
