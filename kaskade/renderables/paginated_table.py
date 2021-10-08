from math import ceil

from rich.table import Table
from rich.text import Text

from kaskade.styles import TABLE_BOX


class PaginatedTable:
    def __init__(self, total_items, page_size=-1, page=1):
        self.total_items = total_items
        self.page_size = total_items if page_size < 0 else page_size
        self.__page = 1
        self.page = page

    def total_pages(self):
        return 0 if self.page_size <= 0 else ceil(self.total_items / self.page_size)

    @property
    def page(self):
        return self.__page

    @page.setter
    def page(self, page):
        if page <= 0:
            self.__page = 1
        elif page > self.total_pages():
            self.__page = self.total_pages()
        else:
            self.__page = page

    def first(self):
        self.page = 1

    def last(self):
        self.page = self.total_pages()

    def previous(self):
        self.page -= 1

    def next(self):
        self.page += 1

    def __rich__(self):
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

        self.render_columns(table)

        if table.columns:
            table.columns[-1].footer = pagination_info
        else:
            return ""

        renderables = self.renderables(self.start_index(), self.end_index()) or []
        self.render_rows(table, renderables)

        if len(table.rows) > self.page_size:
            return f"Rows greater than [yellow bold]{self.page_size}[/]"

        missing_rows = self.page_size - len(table.rows)

        if missing_rows > 0:
            for i in range(missing_rows):
                table.add_row()

        return table

    def start_index(self):
        return (self.page - 1) * self.page_size

    def end_index(self):
        return self.page * self.page_size

    def __str__(self):
        renderables = self.renderables(self.start_index(), self.end_index()) or []
        return str(renderables)

    def render_columns(self, table):
        pass

    def render_rows(self, table, renderables):
        pass

    def renderables(self, start_index, end_index):
        pass


if __name__ == "__main__":
    from rich.console import Console

    class ListPaginatedTable(PaginatedTable):
        def __init__(self, items, page_size=-1, page=1):
            super().__init__(len(items), page_size=page_size, page=page)
            self.items = items

        def renderables(self, start_index, end_index):
            return self.items[start_index:end_index]

        def render_rows(self, table, renderables):
            for item in renderables:
                table.add_row(item)

        def render_columns(self, table):
            table.add_column(
                "name", style="bright_blue", header_style="bright_blue bold"
            )

    console = Console()
    items = ["item {}".format(n + 1) for n in list(range(10))]

    paginated_table = ListPaginatedTable(items, page_size=2)
    console.print(paginated_table)

    paginated_table.next()
    console.print(paginated_table)

    paginated_table.last()
    console.print(paginated_table)

    paginated_table.first()
    console.print(paginated_table)
