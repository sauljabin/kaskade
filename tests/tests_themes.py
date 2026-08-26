import unittest
from unittest.mock import AsyncMock, patch

from textual.containers import ScrollableContainer
from textual.theme import BUILTIN_THEMES, ThemeProvider
from textual.widgets import DataTable, Footer, HelpPanel, OptionList, TabbedContent, TabPane
from textual.widgets._footer import FooterKey

from kaskade.admin import (
    CreateTopicScreen,
    DeleteTopicScreen,
    DescribeTopicScreen,
    EditTopicScreen,
    FilterTopicsScreen,
    KaskadeAdmin,
    ListTopics,
)
from kaskade.consumer import (
    ChunkSizeScreen,
    FilterRecordScreen,
    KaskadeConsumer,
    ListRecords,
    TopicScreen,
)
from kaskade.deserializers import Deserialization
from kaskade.models import Topic
from kaskade.themes import (
    DEFAULT_THEME,
    EVA01_THEME,
    KaskadeApp,
    available_theme_names,
)
from kaskade.widgets import StretchyDataTable


class TestThemes(unittest.TestCase):
    def test_registers_textual_themes_and_eva01_by_default(self):
        app = KaskadeApp()

        self.assertEqual(DEFAULT_THEME, app.theme)
        self.assertEqual(set(BUILTIN_THEMES) | {DEFAULT_THEME}, set(available_theme_names()))
        self.assertIn(DEFAULT_THEME, app.available_themes)

    def test_updates_rich_semantic_styles_when_theme_changes(self):
        app = KaskadeApp()

        self.assertEqual(
            EVA01_THEME.primary.lower(), app.console.get_style("primary").color.get_truecolor().hex
        )

        app.theme = "dracula"

        self.assertEqual("#bd93f9", app.console.get_style("primary").color.get_truecolor().hex)
        self.assertEqual("#6272a4", app.console.get_style("secondary").color.get_truecolor().hex)

    def test_updates_rich_semantic_styles_for_ansi_themes(self):
        app = KaskadeApp()

        for theme in ("ansi-dark", "ansi-light"):
            app.theme = theme

            self.assertEqual("blue", app.console.get_style("primary").color.name)
            self.assertEqual("cyan", app.console.get_style("secondary").color.name)

    def test_uses_textuals_nested_theme_palette(self):
        app = KaskadeApp()

        self.assertTrue(app.use_command_palette)
        self.assertNotIn(ThemeProvider, app.COMMANDS)

    def test_custom_bindings_have_descriptions(self):
        binding_owners = (
            KaskadeApp,
            FilterTopicsScreen,
            DeleteTopicScreen,
            DescribeTopicScreen,
            EditTopicScreen,
            CreateTopicScreen,
            ListTopics,
            FilterRecordScreen,
            ChunkSizeScreen,
            TopicScreen,
            ListRecords,
        )

        for owner in binding_owners:
            with self.subTest(owner=owner.__name__):
                for binding in owner.BINDINGS:
                    self.assertTrue(binding.description)
                    self.assertTrue(binding.description[0].isupper())
                    self.assertTrue(binding.tooltip)

    def test_uses_responsive_screen_breakpoints(self):
        self.assertEqual([(0, "-narrow"), (80, "-wide")], KaskadeApp.HORIZONTAL_BREAKPOINTS)


class TestMainAppLayout(unittest.IsolatedAsyncioTestCase):
    async def test_uses_footer_and_toggles_the_native_help_panel(self):
        with patch("kaskade.admin.TopicService") as topic_service:
            topic_service.return_value.all = AsyncMock(
                return_value={"orders": Topic(name="orders")}
            )
            app = KaskadeAdmin({})

            async with app.run_test() as pilot:
                await pilot.pause()
                table = app.query_one("#topics-table", DataTable)
                active_descriptions = {
                    binding.description for _, binding, _, _ in app.screen.active_bindings.values()
                }

                self.assertIsInstance(app.query_one(Footer), Footer)
                self.assertIs(table, app.screen.focused)
                self.assertTrue(
                    {"Describe", "Filter", "Refresh", "Create", "Quit", "Palette"}
                    <= active_descriptions
                )
                palette_keys = [key for key in app.query(FooterKey) if key.key == "ctrl+p"]
                self.assertEqual(1, len(palette_keys))
                self.assertEqual("Palette", palette_keys[0].description)

                await pilot.press("f1")
                self.assertIsInstance(app.screen.query_one(HelpPanel), HelpPanel)

                await pilot.press("f1")
                self.assertFalse(app.screen.query(HelpPanel))

    async def test_admin_uses_title_case_labels_and_contextual_palette_commands(self):
        with patch("kaskade.admin.TopicService") as topic_service:
            topic_service.return_value.all = AsyncMock(
                return_value={"orders": Topic(name="orders")}
            )
            app = KaskadeAdmin({})

            async with app.run_test() as pilot:
                await pilot.pause()
                table = app.query_one("#topics-table", DataTable)
                labels = [column.label.plain for column in table.columns.values()]
                command_titles = {command.title for command in app.get_system_commands(app.screen)}

                self.assertEqual(
                    [
                        "Name",
                        "Partitions",
                        "Replicas",
                        "In Sync",
                        "Groups",
                        "Members",
                        "Records",
                        "Lag",
                    ],
                    labels,
                )
                self.assertIsInstance(table, StretchyDataTable)
                self.assertFalse(table.show_horizontal_scrollbar)
                self.assertIn("Topics", table.border_title)
                self.assertTrue(
                    {"Theme", "Describe", "Filter", "Refresh", "Create"} <= command_titles
                )
                self.assertTrue({"Maximize", "Minimize"}.isdisjoint(command_titles))

                app.screen.action_maximize()
                await pilot.pause()
                maximized_command_titles = {
                    command.title for command in app.get_system_commands(app.screen)
                }

                self.assertIs(table, app.screen.maximized)
                self.assertTrue({"Maximize", "Minimize"}.isdisjoint(maximized_command_titles))

    async def test_consumer_uses_a_stretchy_records_table(self):
        with patch("kaskade.consumer.ConsumerService") as consumer_service:
            consumer_service.return_value.consume = AsyncMock(return_value=[])
            app = KaskadeConsumer(
                "orders",
                {},
                {},
                {},
                {},
                Deserialization.STRING,
                Deserialization.STRING,
            )

            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                table = app.query_one("#records-table", DataTable)

                self.assertIsInstance(table, StretchyDataTable)
                self.assertEqual(
                    ["Key", "Value", "Timestamp", "Partition", "Offset", "Headers"],
                    [column.label.plain for column in table.ordered_columns],
                )
                self.assertEqual(
                    [23, 9, 9, 9],
                    [column.width for column in table.ordered_columns[2:]],
                )
                self.assertFalse(table.show_horizontal_scrollbar)

    async def test_record_details_focus_the_scrollable_content(self):
        with patch("kaskade.consumer.ConsumerService") as consumer_service:
            consumer_service.return_value.consume = AsyncMock(return_value=[])
            app = KaskadeConsumer(
                "orders",
                {},
                {},
                {},
                {},
                Deserialization.STRING,
                Deserialization.STRING,
            )

            async with app.run_test() as pilot:
                records_table = app.query_one("#records-table", DataTable)
                app.push_screen(TopicScreen("orders", 0, 1, {"value": "record"}))
                await pilot.pause()

                details = app.screen.query_one(".record-details", ScrollableContainer)
                self.assertIs(details, app.screen.focused)

                await pilot.press("escape")
                self.assertIs(records_table, app.screen.focused)

    async def test_topic_details_use_native_tabs_and_a_contextual_footer(self):
        with patch("kaskade.admin.TopicService") as topic_service:
            topic_service.return_value.all = AsyncMock(return_value={})
            app = KaskadeAdmin({})

            async with app.run_test() as pilot:
                app.push_screen(DescribeTopicScreen(Topic(name="orders")))
                await pilot.pause()

                tabs = app.screen.query_one(TabbedContent)
                partitions = app.screen.query_one("#partitions-table", DataTable)
                detail_tables = list(app.screen.query(StretchyDataTable))
                self.assertEqual("partitions", tabs.active)
                self.assertEqual(3, len(app.screen.query(TabPane)))
                self.assertEqual(3, len(app.screen.query(DataTable)))
                self.assertEqual(3, len(detail_tables))
                self.assertGreater(partitions.content_region.height, 0)
                self.assertFalse(partitions.show_horizontal_scrollbar)
                self.assertIsInstance(app.screen.query_one(Footer), Footer)

    async def test_chunk_size_uses_an_option_list_with_the_current_value_selected(self):
        with patch("kaskade.admin.TopicService") as topic_service:
            topic_service.return_value.all = AsyncMock(return_value={})
            app = KaskadeAdmin({})

            async with app.run_test() as pilot:
                app.push_screen(ChunkSizeScreen(100))
                await pilot.pause()

                options = app.screen.query_one(OptionList)
                self.assertEqual(2, options.highlighted)
                self.assertEqual("100", options.get_option_at_index(2).id)
                self.assertEqual(
                    ["25", "50", "100", "500", "1000", "1500"],
                    [option.id for option in options.options],
                )
                self.assertIsInstance(app.screen.query_one(Footer), Footer)

    async def test_renders_dark_light_and_ansi_themes(self):
        for theme in (DEFAULT_THEME, "textual-light", "ansi-light"):
            with self.subTest(theme=theme), patch("kaskade.admin.TopicService") as topic_service:
                topic_service.return_value.all = AsyncMock(return_value={})
                app = KaskadeAdmin({})
                app.theme = theme

                async with app.run_test(size=(80, 24)):
                    screenshot = app.export_screenshot()

                self.assertIn("<svg", screenshot)
