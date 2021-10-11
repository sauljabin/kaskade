from math import ceil
from typing import Any, List, Union

from rich.table import Table
from rich.text import Text

from kaskade.styles import TABLE_BOX


class PaginatedTableStrategy:
    def render_columns(self, table: Table) -> None:
        pass

    def render_rows(self, table: Table, renderables: List[Any]) -> None:
        pass

    def renderables(self, start_index: int, end_index: int) -> List[Any]:
        pass


class PaginatedTable:
    def __init__(
        self,
        strategy: PaginatedTableStrategy,
        total_items: int,
        page_size: int = -1,
        page: int = 1,
    ) -> None:
        self.total_items = total_items
        self.page_size = total_items if page_size < 0 else page_size
        self.__page = 1
        self.page = page
        self.strategy = strategy

    def total_pages(self) -> int:
        return 0 if self.page_size <= 0 else ceil(self.total_items / self.page_size)

    @property
    def page(self) -> int:
        return self.__page

    @page.setter
    def page(self, page: int) -> None:
        if page <= 0:
            self.__page = 1
        elif page > self.total_pages():
            self.__page = self.total_pages()
        else:
            self.__page = page

    def first(self) -> None:
        self.page = 1

    def last(self) -> None:
        self.page = self.total_pages()

    def previous(self) -> None:
        self.page -= 1

    def next(self) -> None:
        self.page += 1

    def __rich__(self) -> Union[Table, str]:
        pagination_info = Text.from_markup(
            "[blue bold]page [yellow bold]{}[/] of [yellow bold]{}[/][/]".format(
                self.page, self.total_pages()
            ),
            justify="right",
        )
        table = Table(
            title_style="",
            expand=True,
            box=TABLE_BOX,
            row_styles=["none", "dim"],
            show_edge=False,
            show_footer=True,
        )

        self.strategy.render_columns(table)

        if table.columns:
            table.columns[-1].footer = pagination_info
        else:
            return ""

        renderables = (
            self.strategy.renderables(self.start_index(), self.end_index()) or []
        )
        self.strategy.render_rows(table, renderables)

        if len(table.rows) > self.page_size:
            return f"Rows greater than [yellow bold]{self.page_size}[/]"

        missing_rows = self.page_size - len(table.rows)

        if missing_rows > 0:
            for i in range(missing_rows):
                table.add_row()

        return table

    def start_index(self) -> int:
        return (self.page - 1) * self.page_size

    def end_index(self) -> int:
        return self.page * self.page_size

    def __str__(self) -> str:
        renderables = (
            self.strategy.renderables(self.start_index(), self.end_index()) or []
        )
        return str(renderables)
