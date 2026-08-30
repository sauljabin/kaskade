import unittest

from textual.app import App, ComposeResult
from textual.widgets import OptionList

from kaskade.widgets import KaskadeOptionList, StretchyDataTable


class StretchyTableApp(App):
    CSS = "StretchyDataTable { border: solid red; height: 100%; }"

    def __init__(self, *, rows: int = 0, wide_columns: bool = False) -> None:
        super().__init__()
        self.rows = rows
        self.wide_columns = wide_columns

    def compose(self) -> ComposeResult:
        table = StretchyDataTable[str]()
        minimum = 10 if self.wide_columns else 4
        table.add_column("First", width=minimum, stretch=1)
        table.add_column("Second", width=minimum, stretch=2)
        table.add_column("Fixed", width=minimum)
        for row in range(self.rows):
            table.add_row(str(row), str(row), str(row))
        yield table


class TestStretchyDataTable(unittest.IsolatedAsyncioTestCase):
    async def test_fills_available_width_and_resizes_proportionally(self):
        app = StretchyTableApp(rows=100)

        async with app.run_test(size=(80, 24)) as pilot:
            table = app.query_one(StretchyDataTable)
            await pilot.pause()

            initial_widths = [column.width for column in table.ordered_columns]
            rendered_width = sum(column.get_render_width(table) for column in table.ordered_columns)
            self.assertEqual(table.scrollable_content_region.width, rendered_width)
            self.assertTrue(table.show_vertical_scrollbar)
            self.assertFalse(table.show_horizontal_scrollbar)
            self.assertEqual(4, initial_widths[2])
            self.assertAlmostEqual(
                2,
                (initial_widths[1] - 4) / (initial_widths[0] - 4),
                delta=0.1,
            )

            await pilot.resize_terminal(120, 30)
            resized_widths = [column.width for column in table.ordered_columns]
            rendered_width = sum(column.get_render_width(table) for column in table.ordered_columns)
            self.assertEqual(table.scrollable_content_region.width, rendered_width)
            self.assertGreater(resized_widths[0], initial_widths[0])
            self.assertGreater(resized_widths[1], initial_widths[1])
            self.assertEqual(initial_widths[2], resized_widths[2])
            self.assertFalse(table.show_horizontal_scrollbar)

    async def test_preserves_minimum_widths_when_the_table_is_too_narrow(self):
        app = StretchyTableApp(wide_columns=True)

        async with app.run_test(size=(20, 10)) as pilot:
            table = app.query_one(StretchyDataTable)
            await pilot.pause()

            self.assertEqual([10, 10, 10], [column.width for column in table.ordered_columns])
            self.assertTrue(table.show_horizontal_scrollbar)

    async def test_accepts_resize_events_before_columns_are_added(self):
        class EmptyTableApp(App):
            def compose(self) -> ComposeResult:
                yield StretchyDataTable()

        app = EmptyTableApp()

        async with app.run_test(size=(40, 10)):
            self.assertEqual([], app.query_one(StretchyDataTable).ordered_columns)


class OptionListApp(App):
    def compose(self) -> ComposeResult:
        yield KaskadeOptionList("alpha", "bravo", "charlie")


class TestKaskadeOptionList(unittest.IsolatedAsyncioTestCase):
    async def test_supports_vim_navigation(self):
        app = OptionListApp()

        async with app.run_test() as pilot:
            option_list = app.query_one(OptionList)
            option_list.highlighted = 0

            await pilot.press("j")
            self.assertEqual(1, option_list.highlighted)
            await pilot.press("k")
            self.assertEqual(0, option_list.highlighted)
            await pilot.press("G")
            self.assertEqual(2, option_list.highlighted)
            await pilot.press("g")
            self.assertEqual(0, option_list.highlighted)
