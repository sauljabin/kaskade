from math import ceil
from typing import Any, List
from unittest import TestCase
from unittest.mock import MagicMock, patch

from rich.table import Table

from kaskade.renderables.paginated_table import PaginatedTable
from tests import faker


class PaginatedTableDummy(PaginatedTable):
    def render_columns(self, table: Table) -> None:
        pass

    def render_rows(self, table: Table, renderables: List[Any]) -> None:
        pass

    def renderables(self, start_index: int, end_index: int) -> List[Any]:
        pass


class TestPaginatedTable(TestCase):
    def test_page_size_is_total_items_when_negative(self):
        total_items = faker.pyint()
        paginated_table = PaginatedTableDummy(total_items, page_size=-1)

        self.assertEqual(total_items, paginated_table.page_size)

    def test_page_size_if_bigger_then_0(self):
        total_items = faker.pyint()
        page_size = 5
        paginated_table = PaginatedTableDummy(total_items, page_size=page_size)

        self.assertEqual(page_size, paginated_table.page_size)

    def test_set_page_if_valid(self):
        total_items = faker.pyint(min_value=10)
        page_size = 2
        page = 2
        paginated_table = PaginatedTableDummy(
            total_items, page_size=page_size, page=page
        )

        self.assertEqual(page, paginated_table.page)

    def test_set_page_if_less_than_0(self):
        total_items = faker.pyint(min_value=10)
        page_size = 2
        page = 1
        paginated_table = PaginatedTableDummy(total_items, page_size=page_size, page=-1)

        self.assertEqual(page, paginated_table.page)

    def test_set_page_if_greater_than_total_pages(self):
        total_items = faker.pyint(min_value=10, max_value=20)
        page_size = 2
        page = 1000000
        paginated_table = PaginatedTableDummy(
            total_items, page_size=page_size, page=page
        )

        self.assertEqual(paginated_table.total_pages(), paginated_table.page)

    def test_total_pages_if_page_size_is_negative(self):
        total_items = faker.pyint()
        paginated_table = PaginatedTableDummy(total_items)

        paginated_table.page_size = -1

        self.assertEqual(0, paginated_table.total_pages())

    def test_total_pages(self):
        total_items = faker.pyint(min_value=1, max_value=9)
        page_size = faker.pyint(min_value=10, max_value=20)
        paginated_table = PaginatedTableDummy(total_items)

        self.assertEqual(ceil(total_items / page_size), paginated_table.total_pages())

    def test_first_page(self):
        total_items = faker.pyint(min_value=10)
        page_size = 2
        page = 2
        paginated_table = PaginatedTableDummy(
            total_items, page_size=page_size, page=page
        )
        paginated_table.first_page()

        self.assertEqual(1, paginated_table.page)

    def test_last_page(self):
        total_items = faker.pyint(min_value=10)
        page_size = 2
        page = 2
        paginated_table = PaginatedTableDummy(
            total_items, page_size=page_size, page=page
        )
        paginated_table.last_page()

        self.assertEqual(paginated_table.total_pages(), paginated_table.page)

    def test_next_page(self):
        total_items = faker.pyint(min_value=10)
        page_size = 2
        page = 2
        paginated_table = PaginatedTableDummy(
            total_items, page_size=page_size, page=page
        )
        paginated_table.next_page()

        self.assertEqual(page + 1, paginated_table.page)

    def test_previous_page(self):
        total_items = faker.pyint(min_value=10)
        page_size = 2
        page = 2
        paginated_table = PaginatedTableDummy(
            total_items, page_size=page_size, page=page
        )
        paginated_table.previous_page()

        self.assertEqual(page - 1, paginated_table.page)

    def test_start_and_end_index(self):
        total_items = faker.pyint(min_value=10)
        page_size = 2
        page = 2
        paginated_table = PaginatedTableDummy(
            total_items, page_size=page_size, page=page
        )

        self.assertEqual((page - 1) * page_size, paginated_table.start_index())
        self.assertEqual(page * page_size, paginated_table.end_index())

    def test_str(self):
        total_items = faker.pyint(min_value=10)
        paginated_table = PaginatedTableDummy(total_items)

        self.assertEqual(str([]), str(paginated_table))

    def test_str_renderables(self):
        total_items = faker.pyint(min_value=10)
        page_size = 2
        page = 2
        paginated_table = PaginatedTableDummy(
            total_items, page_size=page_size, page=page
        )
        renderables = faker.pylist()
        paginated_table.renderables = MagicMock(return_value=renderables)

        self.assertEqual(str(renderables), str(paginated_table))

    @patch("kaskade.renderables.paginated_table.Text.from_markup")
    @patch("kaskade.renderables.paginated_table.Table")
    def test_rich(self, mock_class_table, mock_text_markup):
        total_items = faker.pyint(min_value=10)
        page_size = 2
        page = 2
        paginated_table = PaginatedTableDummy(
            total_items, page_size=page_size, page=page
        )
        paginated_table.render_columns = MagicMock()
        paginated_table.render_rows = MagicMock()
        renderables = faker.pylist()
        paginated_table.renderables = MagicMock(return_value=renderables)

        mock_table = MagicMock()
        mock_class_table.return_value = mock_table
        mock_column = MagicMock()
        mock_table.columns = [mock_column]
        mock_table.rows = ["", ""]

        mock_text = MagicMock()
        mock_text_markup.return_value = mock_text

        paginated_table.__rich__()

        mock_class_table.assert_called_once_with(
            title_style="",
            expand=True,
            box=None,
            show_edge=False,
        )
        paginated_table.render_columns.assert_called_once_with(mock_table)
        paginated_table.render_rows.assert_called_once_with(mock_table, renderables)
        mock_table.add_row.assert_not_called()

    @patch("kaskade.renderables.paginated_table.Table")
    def test_rich_rows_bigger_than_page_size(self, mock_class_table):
        total_items = faker.pyint(min_value=10)
        page_size = 2
        page = 2
        paginated_table = PaginatedTableDummy(
            total_items, page_size=page_size, page=page
        )

        mock_table = MagicMock()
        mock_class_table.return_value = mock_table
        mock_column = MagicMock()
        mock_table.columns = [mock_column]
        mock_table.rows = faker.pylist()

        actual = paginated_table.__rich__()

        self.assertEqual("Rows greater than [yellow bold]2[/]", actual)
