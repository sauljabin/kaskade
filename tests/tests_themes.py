import unittest
from unittest.mock import AsyncMock, patch

from textual.theme import BUILTIN_THEMES
from textual.widgets import DataTable, Footer, HelpPanel, OptionList, TabbedContent, TabPane

from kaskade.admin import (
    CreateTopicScreen,
    DeleteTopicScreen,
    DescribeTopicScreen,
    EditTopicScreen,
    FilterTopicsScreen,
    KaskadeAdmin,
    ListTopics,
)
from kaskade.consumer import ChunkSizeScreen, FilterRecordScreen, ListRecords, TopicScreen
from kaskade.models import Topic
from kaskade.themes import (
    DEFAULT_THEME,
    EVA01_THEME,
    KaskadeApp,
    ThemeProvider,
    available_theme_names,
)


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

    def test_enables_the_command_palette_theme_provider(self):
        app = KaskadeApp()

        self.assertTrue(app.use_command_palette)
        self.assertIn(ThemeProvider, app.COMMANDS)

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
                    {"Describe", "Filter", "Refresh", "Create", "Quit"} <= active_descriptions
                )

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
                self.assertIn("Topics", table.border_title)
                self.assertTrue({"Describe", "Filter", "Refresh", "Create"} <= command_titles)

    async def test_topic_details_use_native_tabs_and_a_contextual_footer(self):
        with patch("kaskade.admin.TopicService") as topic_service:
            topic_service.return_value.all = AsyncMock(return_value={})
            app = KaskadeAdmin({})

            async with app.run_test() as pilot:
                app.push_screen(DescribeTopicScreen(Topic(name="orders")))
                await pilot.pause()

                tabs = app.screen.query_one(TabbedContent)
                partitions = app.screen.query_one("#partitions-table", DataTable)
                self.assertEqual("partitions", tabs.active)
                self.assertEqual(3, len(app.screen.query(TabPane)))
                self.assertEqual(3, len(app.screen.query(DataTable)))
                self.assertGreater(partitions.content_region.height, 0)
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
