import unittest
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import OptionList

from kaskade.themes import KaskadeApp
from kaskade.widgets import KaskadeOptionList, MetadataCell, StretchyDataTable


class TestMetadataCell(unittest.IsolatedAsyncioTestCase):
    async def test_ellipsizes_only_the_label_and_exposes_its_tooltip(self):
        class MetadataApp(KaskadeApp):
            CSS_PATH = Path(__file__).parents[2] / "kaskade/styles.css"
            CSS = "MetadataCell { width: 8; height: 4; }"

            def compose(self) -> ComposeResult:
                yield MetadataCell("Deserializer", "a value that may wrap")

        app = MetadataApp()
        async with app.run_test(size=(20, 8)) as pilot:
            cell = app.query_one(MetadataCell)
            await pilot.pause()

            label, value = cell.render().plain.split("\n", maxsplit=1)
            self.assertEqual("DESERIA…", label)
            self.assertEqual("a value that may wrap", value)
            self.assertEqual("Deserializer", cell.tooltip)

            cell.update_value("updated value")
            self.assertEqual("DESERIA…\nupdated value", cell.render().plain)


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
    async def test_renders_ellipsis_when_row_text_exceeds_column_width(self):
        class TruncatedCellApp(App):
            def compose(self) -> ComposeResult:
                table = StretchyDataTable[str | Text]()
                table.add_column("Value", width=4)
                table.add_row("abcdefgh")
                table.add_row(Text("styled text", style="red"))
                yield table

        app = TruncatedCellApp()
        async with app.run_test(size=(20, 10)) as pilot:
            table = app.query_one(StretchyDataTable)
            await pilot.pause()
            column_width = table.ordered_columns[0].get_render_width(table)

            rendered_rows = []
            for row_index in range(2):
                lines = table._render_cell(
                    row_index,
                    0,
                    table.rich_style,
                    column_width,
                )
                rendered_rows.append("".join(segment.text for segment in lines[0]).strip())

            self.assertEqual(["abc…", "sty…"], rendered_rows)

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

            initial_region_width = table.scrollable_content_region.width
            await pilot.resize_terminal(120, 30)
            for _ in range(10):
                if table.scrollable_content_region.width > initial_region_width:
                    break
                await pilot.pause()

            self.assertGreater(table.scrollable_content_region.width, initial_region_width)
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
