import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from textual.command import CommandList, CommandPalette
from textual.containers import Container, Grid
from textual.coordinate import Coordinate
from textual.geometry import Offset
from textual.selection import Selection
from textual.theme import BUILTIN_THEMES, ThemeProvider
from textual.widgets import (
    Collapsible,
    DataTable,
    Footer,
    Input,
    OptionList,
    RadioSet,
    Static,
    Tab,
    TabbedContent,
    TabPane,
    Tabs,
)

from kaskade import APP_NAME, APP_VERSION
from kaskade.admin import (
    CreateTopicScreen,
    DeleteTopicScreen,
    DescribeTopicScreen,
    EditTopicScreen,
    FilterTopicsScreen,
    KaskadeAdmin,
    ListTopics,
)
from kaskade.app import KaskadeApp
from kaskade.commands import RecordFilters
from kaskade.configs import BOOTSTRAP_SERVERS
from kaskade.consumer import (
    ChunkSizeScreen,
    FilterRecordScreen,
    HeaderDataTable,
    KaskadeConsumer,
    ListRecords,
    TopicScreen,
)
from kaskade.consumer_service import ConsumerSettings
from kaskade.deserializers import Deserialization, StringDeserializer
from kaskade.help import (
    KASKADE_ISSUES_URL,
    KASKADE_URL,
    SELECTED_TEXT_COPY_KEY_DISPLAY,
    SELECTED_TEXT_COPY_SHORTCUT,
    HelpableModalScreen,
    HelpScreen,
)
from kaskade.models import Header, Partition, Record, Topic, TopicConfiguration
from kaskade.settings import AppSettings, load_settings
from kaskade.themes import (
    DEFAULT_THEME,
    EVA01_BERSERK_THEME,
    EVA01_THEME,
    available_theme_names,
    configured_theme_names,
    parse_custom_themes,
)
from kaskade.widgets import (
    KANTRIP_PROFILE,
    KaskadeHeader,
    KaskadeOptionList,
    KaskadeScrollableContainer,
    MetadataCell,
    StretchyDataTable,
    TableFrame,
)
from tests import configure_admin_service, configure_consumer_service


class TestThemes(unittest.TestCase):
    def test_registers_kaskade_themes_and_uses_eva01_berserk_by_default(self):
        app = KaskadeApp()

        self.assertEqual(DEFAULT_THEME, app.theme)
        self.assertEqual("eva01-berserk", DEFAULT_THEME)
        self.assertEqual(
            set(BUILTIN_THEMES) | {EVA01_THEME.name, EVA01_BERSERK_THEME.name},
            set(available_theme_names()),
        )
        self.assertIn(EVA01_THEME.name, app.available_themes)
        self.assertIn(DEFAULT_THEME, app.available_themes)
        self.assertEqual("#9B4DCA", EVA01_THEME.primary)
        self.assertEqual("#2A1845", EVA01_THEME.background)
        self.assertEqual("#1F0E36", EVA01_THEME.surface)
        self.assertEqual("#0E0024", EVA01_THEME.panel)
        self.assertEqual("#0E0024", EVA01_BERSERK_THEME.background)

    def test_updates_rich_semantic_styles_when_theme_changes(self):
        app = KaskadeApp()

        self.assertEqual(
            EVA01_BERSERK_THEME.primary.lower(),
            app.console.get_style("primary").color.get_truecolor().hex,
        )
        self.assertEqual(
            app.get_css_variables()["text-warning"].lower(),
            app.console.get_style("text-warning").color.get_truecolor().hex,
        )
        self.assertTrue(app.console.get_style("muted").dim)
        self.assertEqual(
            app.get_css_variables()["foreground"].lower(),
            app.console.get_style("foreground").color.get_truecolor().hex,
        )

        app.theme = "dracula"

        self.assertEqual("#bd93f9", app.console.get_style("primary").color.get_truecolor().hex)
        self.assertEqual("#6272a4", app.console.get_style("secondary").color.get_truecolor().hex)
        self.assertEqual("#bd93f9", app.console.get_style("json.str").color.get_truecolor().hex)
        self.assertEqual("#6272a4", app.console.get_style("json.number").color.get_truecolor().hex)
        self.assertEqual("#f8f8f2", app.console.get_style("foreground").color.get_truecolor().hex)
        self.assertTrue(app.console.get_style("muted").dim)

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
            HelpableModalScreen,
            HelpScreen,
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
            StretchyDataTable,
            KaskadeOptionList,
            KaskadeScrollableContainer,
        )

        for owner in binding_owners:
            with self.subTest(owner=owner.__name__):
                for binding in owner.BINDINGS:
                    self.assertTrue(binding.description)
                    self.assertTrue(binding.description[0].isupper())
                    self.assertTrue(binding.tooltip)

    def test_uses_responsive_screen_breakpoints(self):
        self.assertEqual([(0, "-narrow"), (80, "-wide")], KaskadeApp.HORIZONTAL_BREAKPOINTS)

    def test_uses_one_shared_stylesheet(self):
        self.assertEqual("styles.css", KaskadeApp.CSS_PATH)
        self.assertEqual(KaskadeApp.CSS_PATH, KaskadeAdmin.CSS_PATH)
        self.assertEqual(KaskadeApp.CSS_PATH, KaskadeConsumer.CSS_PATH)

    def test_modal_commands_match_the_footer_matrix(self):
        expected_commands = {
            FilterTopicsScreen: ["Apply Filter", "Back", "Help"],
            DeleteTopicScreen: ["Delete Topic", "Cancel", "Help"],
            DescribeTopicScreen: ["Back", "Help"],
            EditTopicScreen: ["Save Changes", "Back", "Help"],
            CreateTopicScreen: ["Create Topic", "Back", "Help"],
            FilterRecordScreen: ["Apply Filters", "Back", "Help"],
            ChunkSizeScreen: ["Select", "Back", "Help"],
            TopicScreen: ["Back", "Help"],
            HelpScreen: ["Back"],
        }

        for modal, expected in expected_commands.items():
            with self.subTest(modal=modal.__name__):
                visible_commands = [
                    binding.description for binding in modal.BINDINGS if binding.show
                ]
                self.assertEqual(expected, visible_commands)


SOLARIZED_SETTINGS = """
theme: solarized-kaskade
themes:
  solarized-kaskade:
    primary: "#268BD2"
    secondary: "#2AA198"
    warning: "#B58900"
    error: "#DC322F"
    success: "#859900"
    accent: "#6C71C4"
    foreground: "#839496"
    background: "#002B36"
    surface: "#073642"
    panel: "#002B36"
    boost: "#0A4050"
    dark: true
  minimal-light:
    primary: crimson
    dark: false
  two-tone:
    primary: "#268BD2"
    secondary: "#2AA198"
"""


class TestCustomThemes(unittest.TestCase):
    def settings_path(self, content: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "settings.yaml"
        path.write_text(content, encoding="utf-8")
        return path

    def load_settings(self, content: str) -> AppSettings:
        return load_settings(self.settings_path(content))

    def test_builds_every_supported_property(self):
        themes, warnings = parse_custom_themes(
            {
                "solarized-kaskade": {
                    "primary": "#268bd2",
                    "secondary": "ansi_cyan",
                    "accent": "crimson",
                    "background": "rgb(0, 43, 54)",
                    "dark": True,
                }
            }
        )

        self.assertEqual((), warnings)
        self.assertEqual(1, len(themes))
        theme = themes[0]
        self.assertEqual("solarized-kaskade", theme.name)
        self.assertEqual("#268BD2", theme.primary)
        self.assertEqual("ansi_cyan", theme.secondary)
        self.assertEqual("#DC143C", theme.accent)
        self.assertEqual("#002B36", theme.background)
        self.assertIsNone(theme.surface)
        self.assertTrue(theme.dark)

    def test_ignores_invalid_names_and_collisions(self):
        themes, warnings = parse_custom_themes(
            {
                "Solarized": {"primary": "#268BD2"},
                "double--hyphen": {"primary": "#268BD2"},
                1: {"primary": "#268BD2"},
                "dracula": {"primary": "#268BD2"},
                "eva01": {"primary": "#268BD2"},
                "not-a-mapping": "#268BD2",
            }
        )

        self.assertEqual((), themes)
        name_reason = "names use lowercase letters, digits, and single hyphens"
        self.assertEqual(
            (
                f"Ignoring 'themes.Solarized': {name_reason}",
                f"Ignoring 'themes.double--hyphen': {name_reason}",
                f"Ignoring 'themes.1': {name_reason}",
                "Ignoring 'themes.dracula': a built-in theme already uses this name",
                "Ignoring 'themes.eva01': a built-in theme already uses this name",
                "Ignoring 'themes.not-a-mapping': it must be a mapping",
            ),
            warnings,
        )

    def test_ignores_invalid_properties_and_keeps_valid_ones(self):
        themes, warnings = parse_custom_themes(
            {
                "partial": {
                    "primary": "#268BD2",
                    "secondary": None,
                    "surface": "#07364280",
                    "panel": "not-a-color",
                    "dark": "yes",
                    "shadow": "#000000",
                    "accent": "#6C71C4",
                }
            }
        )

        self.assertEqual(1, len(themes))
        self.assertEqual("#268BD2", themes[0].primary)
        self.assertEqual("#6C71C4", themes[0].accent)
        self.assertIsNone(themes[0].secondary)
        self.assertIsNone(themes[0].surface)
        self.assertIsNone(themes[0].panel)
        self.assertTrue(themes[0].dark)
        color_reason = 'it must be an opaque color such as "#268BD2"; quote hex colors in YAML'
        self.assertEqual(
            (
                f"Ignoring 'themes.partial.secondary': {color_reason}",
                f"Ignoring 'themes.partial.surface': {color_reason}",
                f"Ignoring 'themes.partial.panel': {color_reason}",
                "Ignoring 'themes.partial.dark': it must be true or false",
                "Ignoring 'themes.partial.shadow': unknown theme property",
            ),
            warnings,
        )

    def test_requires_a_valid_primary_color(self):
        themes, warnings = parse_custom_themes(
            {"missing": {"background": "#002B36"}, "unquoted": {"primary": None}}
        )

        self.assertEqual((), themes)
        color_reason = 'it must be an opaque color such as "#268BD2"; quote hex colors in YAML'
        self.assertEqual(
            (
                "Ignoring 'themes.missing': it needs a valid 'primary' color",
                f"Ignoring 'themes.unquoted.primary': {color_reason}",
                "Ignoring 'themes.unquoted': it needs a valid 'primary' color",
            ),
            warnings,
        )

    def test_selects_a_custom_theme_from_settings(self):
        app = KaskadeApp(settings=self.load_settings(SOLARIZED_SETTINGS))

        self.assertEqual("solarized-kaskade", app.theme)
        self.assertEqual((), app.settings.warnings)
        self.assertIn("minimal-light", app.available_themes)
        self.assertEqual("#268bd2", app.console.get_style("primary").color.get_truecolor().hex)
        self.assertEqual("#2aa198", app.console.get_style("json.number").color.get_truecolor().hex)
        self.assertEqual("#002B36", app.get_css_variables()["background"])

    def test_rich_styles_follow_a_minimal_custom_theme(self):
        app = KaskadeApp(settings=self.load_settings(SOLARIZED_SETTINGS))

        app.theme = "minimal-light"

        self.assertFalse(app.current_theme.dark)
        for style in ("primary", "secondary", "accent", "json.key", "json.null"):
            self.assertEqual("#dc143c", app.console.get_style(style).color.get_truecolor().hex)

    def test_rich_error_and_success_fall_back_to_secondary_like_textual(self):
        app = KaskadeApp(settings=self.load_settings(SOLARIZED_SETTINGS))

        app.theme = "two-tone"

        css = app.get_css_variables()
        for style, variable in (
            ("error", "error"),
            ("success", "success"),
            ("json.bool_false", "error"),
            ("json.bool_true", "success"),
            ("warning", "warning"),
            ("accent", "accent"),
        ):
            self.assertEqual(
                css[variable].lower(),
                app.console.get_style(style).color.get_truecolor().hex,
                style,
            )
        self.assertEqual("#2aa198", app.console.get_style("error").color.get_truecolor().hex)
        self.assertEqual("#268bd2", app.console.get_style("warning").color.get_truecolor().hex)

    def test_invalid_selected_custom_theme_falls_back_to_the_default(self):
        app = KaskadeApp(
            settings=self.load_settings(
                'theme: broken\nthemes:\n  broken:\n    background: "#002B36"\n'
            )
        )

        self.assertEqual(DEFAULT_THEME, app.theme)
        self.assertEqual(
            (
                "Ignoring 'themes.broken': it needs a valid 'primary' color",
                "Ignoring 'theme': unknown theme 'broken'",
            ),
            app.settings.warnings,
        )

    def test_colliding_custom_theme_keeps_the_built_in_theme(self):
        app = KaskadeApp(
            settings=self.load_settings(
                'theme: dracula\nthemes:\n  dracula:\n    primary: "#268BD2"\n'
            )
        )

        self.assertEqual("dracula", app.theme)
        self.assertEqual("#BD93F9", app.current_theme.primary)
        self.assertEqual(
            ("Ignoring 'themes.dracula': a built-in theme already uses this name",),
            app.settings.warnings,
        )

    def test_themes_must_be_a_mapping(self):
        app = KaskadeApp(settings=self.load_settings("themes: [solarized]\n"))

        self.assertEqual(DEFAULT_THEME, app.theme)
        self.assertEqual(("Ignoring 'themes': it must be a mapping",), app.settings.warnings)

    def test_example_settings_define_a_valid_custom_theme(self):
        example = Path(__file__).parents[2] / "examples" / "settings.yaml"

        app = KaskadeApp(settings=load_settings(example))

        self.assertEqual((), app.settings.warnings)
        self.assertEqual(DEFAULT_THEME, app.theme)
        self.assertIn("solarized-kaskade", app.available_themes)

    def test_configured_theme_names_include_valid_custom_themes(self):
        names = configured_theme_names(self.settings_path(SOLARIZED_SETTINGS))

        self.assertIn("solarized-kaskade", names)
        self.assertIn("minimal-light", names)
        self.assertTrue(set(available_theme_names()) <= set(names))


class TestMainAppLayout(unittest.IsolatedAsyncioTestCase):
    async def test_themes_use_one_shared_semantic_surface_treatment(self):
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})

            async with app.run_test() as pilot:
                header = app.query_one(KaskadeHeader)
                table = app.query_one("#topics-table", DataTable)
                footer = app.query_one(Footer)

                for theme in (
                    EVA01_THEME.name,
                    EVA01_BERSERK_THEME.name,
                    "textual-light",
                    "dracula",
                ):
                    with self.subTest(theme=theme):
                        app.theme = theme
                        await pilot.pause()

                        self.assertEqual(
                            app.current_theme.background,
                            app.screen.styles.background.hex,
                        )
                        self.assertEqual(
                            app.current_theme.background,
                            header.styles.background.hex,
                        )
                        self.assertEqual(
                            0,
                            table.get_component_styles("datatable--header").background.a,
                        )
                        self.assertEqual(
                            app.current_theme.background,
                            footer.styles.background.hex,
                        )

    async def test_header_updates_semantic_colors_when_theme_changes(self):
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})

            async with app.run_test() as pilot:
                product = app.query_one("#kaskade-product", Static)

                for theme in ("textual-light", "dracula", DEFAULT_THEME):
                    app.theme = theme
                    await pilot.pause()

                    product_text = product.render()
                    self.assertEqual(
                        [
                            app.current_theme.primary.lower(),
                            (app.current_theme.secondary or app.current_theme.primary).lower(),
                        ],
                        [span.style.foreground.hex.lower() for span in product_text.spans],
                    )

    async def test_uses_footer_and_opens_a_keyboard_navigable_help_window(self):
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(
                topic_service.return_value,
                {
                    "orders": Topic(name="orders"),
                    "payments": Topic(name="payments"),
                },
            )
            app = KaskadeAdmin({})

            async with app.run_test(size=(70, 18)) as pilot:
                await pilot.pause()
                table = app.query_one("#topics-table", DataTable)
                frame = app.query_one("#topics-frame", TableFrame)
                header = app.query_one(KaskadeHeader)
                product = header.query_one("#kaskade-product", Static)
                kafka = header.query_one("#kaskade-kafka", Static)
                active_descriptions = {
                    binding.description for _, binding, _, _ in app.screen.active_bindings.values()
                }

                product_text = product.render()
                self.assertEqual(f"Kaskade v{APP_VERSION}", product_text.plain)
                self.assertEqual(
                    [app.current_theme.primary, app.current_theme.secondary],
                    [span.style.foreground.hex for span in product_text.spans],
                )
                self.assertEqual("Not configured", kafka.render().plain)
                self.assertTrue(app.screen.has_class("main-view-screen"))
                self.assertEqual(1, app.screen.styles.padding.left)
                self.assertEqual(1, app.screen.styles.padding.right)
                self.assertEqual(1, header.styles.padding.top)
                self.assertEqual(1, header.styles.padding.bottom)
                self.assertEqual(app.current_theme.background, header.styles.background.hex)
                self.assertEqual(header.styles.background, app.screen.styles.background)
                self.assertEqual(0, table.styles.background.a)
                self.assertFalse(table.zebra_stripes)
                self.assertEqual(
                    app.get_css_variables()["primary-darken-3"].lower(),
                    table.get_component_styles("datatable--cursor").background.hex6.lower(),
                )
                self.assertEqual(
                    0.85,
                    table.get_component_styles("datatable--cursor").background.a,
                )
                self.assertEqual(
                    0,
                    table.get_component_styles("datatable--header").background.a,
                )
                self.assertEqual(
                    app.get_css_variables()["text-secondary"].lower(),
                    table.get_component_styles("datatable--header").color.hex.lower(),
                )
                self.assertEqual(
                    0,
                    table.get_component_styles("datatable--header-hover").background.a,
                )
                self.assertEqual(
                    0,
                    table.get_component_styles("datatable--header").background_tint.a,
                )
                self.assertEqual("", table.styles.border_top[0])
                self.assertNotEqual("", frame.styles.border_top[0])
                self.assertGreater(frame.styles.border_top[1].a, 0)
                footer = app.query_one(Footer)
                self.assertIsInstance(footer, Footer)
                self.assertEqual(app.current_theme.background, footer.styles.background.hex)
                for widget in (header, frame, footer):
                    self.assertEqual(1, widget.region.x)
                    self.assertEqual(app.screen.region.right - 1, widget.region.right)
                self.assertEqual(0, header.region.y)
                self.assertEqual(1, header.content_region.y)
                self.assertEqual(header.region.bottom, frame.region.y)
                self.assertEqual(frame.content_region, table.region)
                self.assertIs(table, app.screen.focused)
                self.assertTrue(
                    {"Describe", "Filter", "Refresh", "Create", "Quit", "Commands"}
                    <= active_descriptions
                )
                palette_keys = [key for key in app.query("FooterKey") if key.key_display == ":"]
                self.assertEqual(1, len(palette_keys))
                self.assertEqual("Commands", palette_keys[0].description)
                self.assertEqual(
                    ["Quit", "Help", "Commands"],
                    [key.description for key in app.query("FooterKey")][-3:],
                )

                await pilot.press("?")
                self.assertIsInstance(app.screen, HelpScreen)

                help_screen = app.screen
                help_dialog = help_screen.query_one("#help-dialog")
                help_table = help_screen.query_one("#help-table", DataTable)
                help_heading = help_screen.query_one("#help-heading", Static)
                help_about = help_screen.query_one("#help-about", Static)
                help_footer = help_screen.query_one(Footer)
                self.assertEqual(help_screen.size.width, help_dialog.region.width)
                await pilot.resize_terminal(120, 30)
                await pilot.pause()
                self.assertEqual(72, help_dialog.region.width)
                await pilot.resize_terminal(70, 18)
                await pilot.pause()
                self.assertEqual(help_screen.size.width, help_dialog.region.width)
                self.assertEqual(app.current_theme.background, help_dialog.styles.background.hex)
                self.assertEqual(
                    [help_heading, help_about, help_table],
                    list(help_dialog.children)[:3],
                )
                self.assertEqual("[primary]Help[/primary] — Topics", help_dialog.border_title)
                self.assertEqual(f"{APP_NAME.title()} v{APP_VERSION}", help_heading.render().plain)
                self.assertEqual(1, help_about.styles.margin.bottom)
                self.assertIsNone(help_table.border_title)
                help_footer_keys = list(help_footer.query("FooterKey"))
                self.assertEqual(1, len(help_footer_keys))
                self.assertEqual("esc", help_footer_keys[0].key_display)
                self.assertEqual("Back", help_footer_keys[0].description)
                about_text = help_about.render().plain
                self.assertIn("About Kaskade", about_text)
                self.assertIn(KASKADE_URL, about_text)
                self.assertIn(KASKADE_ISSUES_URL, about_text)
                self.assertIs(help_table, help_screen.focused)
                self.assertFalse(help_table.zebra_stripes)
                self.assertEqual(0, help_table.cursor_row)
                help_header_styles = help_table.get_component_styles("datatable--header")
                self.assertEqual(0, help_header_styles.background.a)
                self.assertEqual(
                    app.get_css_variables()["text-secondary"].lower(),
                    help_header_styles.color.hex.lower(),
                )
                self.assertEqual(0, help_header_styles.background_tint.a)
                self.assertTrue(
                    {
                        "Copy Selected Text",
                        "Copy Topic",
                        "Describe",
                        "Filter",
                        "Refresh",
                        "Create",
                        "Quit",
                        "Commands",
                    }
                    <= {binding.description for binding in help_screen.help_bindings}
                )
                self.assertIn("Topics", {binding.context for binding in help_screen.help_bindings})
                quit_binding = next(
                    binding
                    for binding in help_screen.help_bindings
                    if binding.description == "Quit"
                )
                self.assertEqual(("^c",), quit_binding.keys)
                binding_keys = {
                    binding.description: binding.keys for binding in help_screen.help_bindings
                }
                self.assertEqual(("?", "f1"), binding_keys["Help"])
                self.assertEqual((":", "^p"), binding_keys["Commands"])
                self.assertEqual(("d", "⏎"), binding_keys["Describe"])
                self.assertEqual(("y",), binding_keys["Copy Topic"])
                selected_text_copy_display = SELECTED_TEXT_COPY_KEY_DISPLAY or "shift+^c"
                self.assertEqual(
                    (selected_text_copy_display,),
                    binding_keys["Copy Selected Text"],
                )
                self.assertNotIn(
                    "ctrl+c",
                    binding_keys["Copy Selected Text"],
                )
                await pilot.press("pagedown")
                await pilot.pause()
                self.assertGreater(help_table.cursor_row, 0)
                self.assertEqual(0, table.cursor_row)

                await pilot.press("?")
                self.assertNotIsInstance(app.screen, HelpScreen)
                self.assertIs(table, app.screen.focused)

                await pilot.press("j")
                self.assertEqual(1, table.cursor_row)

                await pilot.press(":")
                self.assertIsInstance(app.screen, CommandPalette)
                app.screen.add_class("-ready")
                await pilot.pause()
                palette_container = app.screen.query_one("#--container")
                palette_input = app.screen.query_one("#--input")
                self.assertEqual(
                    app.current_theme.background,
                    palette_container.styles.background.hex,
                )
                self.assertEqual(70, palette_input.region.width)

                await pilot.resize_terminal(120, 30)
                await pilot.pause()
                self.assertEqual(72, palette_input.region.width)

                palette_input.value = "help"
                await pilot.pause()
                command_list = app.screen.query_one(CommandList)
                command_list.highlighted = next(
                    index
                    for index in range(command_list.option_count)
                    if command_list.get_option_at_index(index).hit.text == "Help"
                )
                palette_selection = command_list.get_component_styles(
                    "option-list--option-highlighted"
                )
                self.assertEqual(
                    app.get_css_variables()["primary-darken-3"].lower(),
                    palette_selection.background.hex6.lower(),
                )
                self.assertEqual(0.85, palette_selection.background.a)
                await pilot.press("enter")
                await pilot.pause()

                self.assertIsInstance(app.screen, HelpScreen)
                self.assertEqual("Topics", app.screen.context)

    async def test_admin_supports_vim_navigation(self):
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(
                topic_service.return_value,
                {
                    "alpha": Topic(name="alpha"),
                    "bravo": Topic(name="bravo"),
                    "charlie": Topic(name="charlie"),
                },
            )
            app = KaskadeAdmin({})

            async with app.run_test() as pilot:
                await pilot.pause()
                table = app.query_one("#topics-table", DataTable)

                self.assertEqual(0, table.cursor_row)
                await pilot.press("j")
                self.assertEqual(1, table.cursor_row)
                await pilot.press("k")
                self.assertEqual(0, table.cursor_row)
                await pilot.press("G")
                self.assertEqual(2, table.cursor_row)
                await pilot.press("g")
                self.assertEqual(0, table.cursor_row)

    async def test_plain_shortcuts_do_not_intercept_filter_input(self):
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})

            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("/")
                await pilot.pause()
                filter_input = app.screen.query_one("#topic-filter", Input)

                await pilot.press(":", "?")

                self.assertEqual(":?", filter_input.value)
                self.assertNotIsInstance(app.screen, HelpScreen)

                await pilot.press("f1")
                self.assertIsInstance(app.screen, HelpScreen)
                self.assertEqual("Filter Topics", app.screen.context)

                await pilot.press("escape")
                self.assertIsInstance(app.screen, FilterTopicsScreen)
                self.assertIs(filter_input, app.screen.focused)

    async def test_modal_footers_show_and_run_implicit_submit_actions(self):
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})
            results: list[object] = []

            async with app.run_test() as pilot:

                def footer_commands() -> list[tuple[str, str]]:
                    footer = app.screen.query_one(Footer)
                    return [(key.key_display, key.description) for key in footer.query("FooterKey")]

                app.push_screen(FilterTopicsScreen(), results.append)
                await pilot.pause()
                self.assertEqual(
                    [("⏎", "Apply Filter"), ("esc", "Back"), ("?", "Help")],
                    footer_commands(),
                )
                app.screen.query_one("#topic-filter", Input).value = "orders"
                await pilot.press("enter")
                self.assertEqual("orders", results.pop())

                app.push_screen(DeleteTopicScreen(Topic(name="orders")), results.append)
                await pilot.pause()
                self.assertEqual(
                    [("⏎", "Delete Topic"), ("esc", "Cancel"), ("?", "Help")],
                    footer_commands(),
                )
                app.screen.query_one("#topic-confirmation", Input).value = "orders"
                await pilot.press("enter")
                self.assertIs(True, results.pop())

                app.push_screen(FilterRecordScreen(), results.append)
                await pilot.pause()
                self.assertEqual(
                    [("⏎", "Apply Filters"), ("esc", "Back"), ("?", "Help")],
                    footer_commands(),
                )
                app.screen.query_one("#key", Input).value = "customer"
                await pilot.press("enter")
                self.assertEqual(RecordFilters(key="customer"), results.pop())

                app.push_screen(ChunkSizeScreen(100), results.append)
                await pilot.pause()
                chunk_sizes = app.screen.query_one(OptionList)
                self.assertEqual(0, chunk_sizes.styles.background.a)
                self.assertEqual(0, chunk_sizes.styles.background_tint.a)
                chunk_selection = chunk_sizes.get_component_styles(
                    "option-list--option-highlighted"
                )
                self.assertEqual(
                    app.get_css_variables()["primary-darken-3"].lower(),
                    chunk_selection.background.hex6.lower(),
                )
                self.assertEqual(0.85, chunk_selection.background.a)
                self.assertEqual(
                    [("⏎", "Select"), ("esc", "Back"), ("?", "Help")],
                    footer_commands(),
                )
                await pilot.press("enter")
                self.assertEqual(100, results.pop())

                app.push_screen(CreateTopicScreen(), results.append)
                await pilot.pause()
                self.assertEqual(
                    [("^s", "Create Topic"), ("esc", "Back"), ("?", "Help")],
                    footer_commands(),
                )
                fields = list(app.screen.query(Input))
                radio_set = app.screen.query_one(RadioSet)
                collapsible = app.screen.query_one(Collapsible)
                collapsible_title = collapsible.query_one("CollapsibleTitle")
                self.assertTrue(fields)
                self.assertTrue(all(field.styles.background.a == 0 for field in fields))
                self.assertEqual(0, radio_set.styles.background.a)
                self.assertEqual(0, collapsible.styles.background.a)
                self.assertEqual(0, collapsible_title.styles.background.a)
                await pilot.click(collapsible_title)
                await pilot.pause()
                self.assertIs(collapsible_title, app.screen.focused)
                self.assertGreater(collapsible_title.styles.background.a, 0)
                await pilot.press("f1")
                create_binding = next(
                    binding
                    for binding in app.screen.help_bindings
                    if binding.description == "Create Topic"
                )
                self.assertEqual(("^s", "shift+^s", "f2"), create_binding.keys)
                await pilot.press("escape")
                await pilot.press("escape")

                app.push_screen(
                    EditTopicScreen(
                        Topic(name="orders", partitions=[Partition(id=0)]),
                        {
                            "min.insync.replicas": "1",
                            "cleanup.policy": "delete",
                            "retention.ms": "1000",
                        },
                    ),
                    results.append,
                )
                await pilot.pause()
                self.assertEqual(
                    [("^s", "Save Changes"), ("esc", "Back"), ("?", "Help")],
                    footer_commands(),
                )
                await pilot.press("escape")

    async def test_admin_uses_title_case_labels_and_contextual_palette_commands(self):
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(
                topic_service.return_value,
                {"orders": Topic(name="orders")},
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
                self.assertIn(
                    "Topics",
                    app.query_one("#topics-frame", TableFrame).border_title,
                )
                self.assertTrue(
                    {
                        "Theme",
                        "Quit",
                        "Help",
                        "Screenshot",
                        "Copy Topic",
                        "Describe",
                        "Filter",
                        "Refresh",
                        "Create",
                    }
                    <= command_titles
                )
                self.assertNotIn("Keys", command_titles)
                self.assertTrue({"Maximize", "Minimize"}.isdisjoint(command_titles))

                app.screen.action_maximize()
                await pilot.pause()
                maximized_command_titles = {
                    command.title for command in app.get_system_commands(app.screen)
                }

                self.assertIs(table, app.screen.maximized)
                self.assertTrue({"Maximize", "Minimize"}.isdisjoint(maximized_command_titles))

    async def test_selected_text_copy_is_separate_from_ctrl_c_quit(self):
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {"orders": Topic(name="orders")})
            app = KaskadeAdmin({})

            async with app.run_test() as pilot:
                await pilot.pause()
                product = app.query_one("#kaskade-product", Static)
                app.screen.selections = {
                    product: Selection(Offset(0, 0), Offset(len("Kaskade"), 0))
                }

                await pilot.press(SELECTED_TEXT_COPY_SHORTCUT)

                self.assertEqual("Kaskade", app.clipboard)

                app.copy_to_clipboard("")
                app.screen.clear_selection()
                await pilot.press(SELECTED_TEXT_COPY_SHORTCUT)
                self.assertEqual("", app.clipboard)

                app.screen.selections = {
                    product: Selection(Offset(0, 0), Offset(len("Kaskade"), 0))
                }
                app.exit = MagicMock()
                app.push_screen(FilterTopicsScreen())
                await pilot.pause()

                await pilot.press("ctrl+c")

                app.exit.assert_called_once_with()
                self.assertEqual("", app.clipboard)
                app.exit.reset_mock()
                await pilot.press("escape")

                await pilot.press("ctrl+c")

                app.exit.assert_called_once_with()
                self.assertEqual("", app.clipboard)

    async def test_consumer_uses_a_stretchy_records_table(self):
        with patch("kaskade.consumer.app.ConsumerService") as consumer_service:
            configure_consumer_service(consumer_service.return_value)
            bootstrap_servers = "kafka1:9092,kafka2:9092"
            app = KaskadeConsumer(
                ConsumerSettings(
                    "orders",
                    {BOOTSTRAP_SERVERS: bootstrap_servers},
                    Deserialization.STRING,
                    Deserialization.STRING,
                )
            )

            async with app.run_test(size=(100, 24)) as pilot:
                await pilot.pause()
                table = app.query_one("#records-table", DataTable)
                header = app.query_one(KaskadeHeader)

                self.assertEqual(
                    f"Kaskade v{APP_VERSION}",
                    header.query_one("#kaskade-product", Static).render().plain,
                )
                self.assertEqual(
                    "kafka1:9092",
                    header.query_one("#kaskade-kafka", Static).render().plain,
                )
                self.assertIsInstance(table, StretchyDataTable)
                self.assertFalse(table.zebra_stripes)
                self.assertIs(table, app.screen.focused)
                self.assertEqual(
                    ["Key", "Value", "Size", "Timestamp", "Partition", "Offset", "Headers"],
                    [column.label.plain for column in table.ordered_columns],
                )
                self.assertEqual(
                    [10, 23, 9, 6, 7],
                    [column.width for column in table.ordered_columns[2:]],
                )
                self.assertFalse(table.show_horizontal_scrollbar)

    async def test_header_constrains_kafka_information_on_narrow_terminals(self):
        bootstrap_servers = "[::1]:9092,kafka2.example.com:9092"
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({BOOTSTRAP_SERVERS: bootstrap_servers})

            async with app.run_test(size=(24, 18)) as pilot:
                await pilot.pause()
                header = app.query_one(KaskadeHeader)
                product = header.query_one("#kaskade-product", Static)
                kafka = header.query_one("#kaskade-kafka", Static)

                self.assertEqual(f"Kaskade v{APP_VERSION}", product.render().plain)
                self.assertEqual("[::1]:9092", kafka.render().plain)
                self.assertEqual(3, header.region.height)
                self.assertEqual(app.screen.content_region.width, header.region.width)
                self.assertEqual(
                    header.content_region.width,
                    product.region.width + kafka.region.width,
                )
                self.assertLess(kafka.content_region.width, len(kafka.render().plain))
                self.assertEqual("ellipsis", kafka.styles.text_overflow)

    async def test_header_shows_kantrip_profile_before_bootstrap_server(self):
        environment = {
            KANTRIP_PROFILE: " staging [bold]eu[/] ",
            "KANTRIP_SESSION_ID": "session-secret",
        }
        with (
            patch.dict(os.environ, environment),
            patch("kaskade.admin.app.TopicService") as topic_service,
            patch("kaskade.consumer.app.ConsumerService") as consumer_service,
        ):
            configure_admin_service(topic_service.return_value, {})
            configure_consumer_service(consumer_service.return_value)
            apps = {
                "admin": KaskadeAdmin({BOOTSTRAP_SERVERS: "kafka1:9092"}),
                "consumer": KaskadeConsumer(
                    ConsumerSettings(
                        "orders",
                        {BOOTSTRAP_SERVERS: "kafka1:9092"},
                        Deserialization.STRING,
                        Deserialization.STRING,
                    )
                ),
            }

            for mode, app in apps.items():
                with self.subTest(mode=mode):
                    async with app.run_test(size=(100, 24)) as pilot:
                        await pilot.pause()
                        header = app.query_one(KaskadeHeader)
                        kafka = header.query_one("#kaskade-kafka", Static)
                        connection = kafka.render()
                        profile_style = connection.get_style_at_offset(0)

                        self.assertEqual(
                            "staging [bold]eu[/] · kafka1:9092",
                            connection.plain,
                        )
                        self.assertTrue(profile_style.bold)
                        self.assertEqual(
                            app.get_css_variables()["foreground"].lower(),
                            profile_style.foreground.hex.lower(),
                        )
                        self.assertEqual(3, header.region.height)
                        self.assertNotIn(
                            "session-secret",
                            " ".join(static.render().plain for static in header.query(Static)),
                        )

    async def test_header_truncates_bootstrap_server_before_kantrip_profile(self):
        with (
            patch.dict(os.environ, {KANTRIP_PROFILE: "staging"}),
            patch("kaskade.admin.app.TopicService") as topic_service,
        ):
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({BOOTSTRAP_SERVERS: "kafka1.example.com:9092"})

            async with app.run_test(size=(40, 18)) as pilot:
                await pilot.pause()
                header = app.query_one(KaskadeHeader)
                product = header.query_one("#kaskade-product", Static)
                kafka = header.query_one("#kaskade-kafka", Static)
                visible = kafka.render_line(0).text

                self.assertTrue(visible.startswith("staging · kafka1"))
                self.assertEqual(product.region.right + 1, kafka.content_region.x)
                self.assertTrue(visible.rstrip().endswith("…"))
                self.assertEqual(3, header.region.height)

    async def test_header_keeps_layout_without_kantrip_profile(self):
        for value in (None, "", "   "):
            environment = {} if value is None else {KANTRIP_PROFILE: value}
            with (
                self.subTest(profile=value),
                patch.dict(os.environ, environment),
                patch("kaskade.admin.app.TopicService") as topic_service,
            ):
                if value is None:
                    os.environ.pop(KANTRIP_PROFILE, None)
                configure_admin_service(topic_service.return_value, {})
                app = KaskadeAdmin({BOOTSTRAP_SERVERS: "kafka1:9092"})

                async with app.run_test(size=(100, 24)) as pilot:
                    await pilot.pause()
                    header = app.query_one(KaskadeHeader)
                    connection = header.query_one("#kaskade-kafka", Static).render()

                    self.assertEqual("kafka1:9092", connection.plain)
                    self.assertEqual([], connection.spans)
                    self.assertEqual(3, header.region.height)

    async def test_record_details_use_native_tabs_and_fill_narrow_layout(self):
        with patch("kaskade.consumer.app.ConsumerService") as consumer_service:
            configure_consumer_service(consumer_service.return_value)
            app = KaskadeConsumer(
                ConsumerSettings("orders", {}, Deserialization.STRING, Deserialization.STRING)
            )

            async with app.run_test(size=(60, 24)) as pilot:
                records_table = app.query_one("#records-table", DataTable)
                app.push_screen(
                    TopicScreen(
                        Record(
                            topic="orders",
                            partition=0,
                            offset=1,
                            key=b"key",
                            value=b"value",
                            headers=[Header("long-header-key", b"value", StringDeserializer())],
                        )
                    )
                )
                await pilot.pause()

                details = app.screen.query_one(".record-details", Container)
                tabs = app.screen.query_one(Tabs)
                self.assertIs(tabs, app.screen.focused)
                self.assertEqual(app.screen.content_region.width, details.region.width)
                self.assertEqual(app.current_theme.background, details.styles.background.hex)
                self.assertEqual(
                    ["Key", "Value", "Headers [1]", "Export"],
                    [tab.label_text for tab in app.screen.query(Tab)],
                )
                self.assertEqual(4, len(app.screen.query(TabPane)))
                self.assertIsInstance(app.screen.query_one(Footer), Footer)
                metadata = app.screen.query_one("#record-metadata", Grid)
                metadata_cells = list(metadata.query(".record-metadata-cell"))
                self.assertEqual(2, metadata.styles.grid_size_columns)
                self.assertEqual(2, metadata.styles.grid_size_rows)
                self.assertEqual(metadata_cells[0].region.y, metadata_cells[1].region.y)
                self.assertGreater(metadata_cells[2].region.y, metadata_cells[0].region.y)
                self.assertTrue(
                    all(cell.styles.border_top[0] == "solid" for cell in metadata_cells)
                )
                self.assertTrue(all(cell.content_region.height == 2 for cell in metadata_cells))
                diagnostics = app.screen.query_one(".record-diagnostics", Grid)
                self.assertEqual(1, diagnostics.styles.grid_size_columns)
                self.assertEqual(3, diagnostics.styles.grid_size_rows)
                self.assertTrue(
                    all(
                        cell.content_region.height == 2
                        for cell in diagnostics.query(".record-diagnostic")
                    )
                )
                content = app.screen.query_one("#record-key-details .record-content", Static)
                content_panel = app.get_css_variables()["panel-darken-1"]
                self.assertEqual(content_panel, content.styles.background.hex)
                self.assertNotEqual(details.styles.background, content.styles.background)

                key_scroll = app.screen.query_one(
                    "#key .record-detail-scroll", KaskadeScrollableContainer
                )
                await pilot.press("tab")
                self.assertIs(key_scroll, app.screen.focused)
                await pilot.pause()
                focused_panel = app.get_css_variables()["panel"]
                self.assertEqual(focused_panel, content.styles.background.hex)

                await pilot.press("tab")
                self.assertIs(tabs, app.screen.focused)
                await pilot.press("right")
                self.assertEqual("value", app.screen.query_one(TabbedContent).active)
                value_scroll = app.screen.query_one(
                    "#value .record-detail-scroll", KaskadeScrollableContainer
                )
                await pilot.press("tab")
                self.assertIs(value_scroll, app.screen.focused)
                await pilot.pause()
                value_content = app.screen.query_one(
                    "#record-value-details .record-content", Static
                )
                self.assertEqual(focused_panel, value_content.styles.background.hex)
                self.assertEqual(content_panel, content.styles.background.hex)

                tabs.focus()
                app.screen.query_one(TabbedContent).active = "headers"
                await pilot.pause()
                header_list = app.screen.query_one("#record-headers-list", HeaderDataTable)
                header_details = app.screen.query_one(".record-header-details", Container)
                self.assertFalse(header_list.show_header)
                self.assertLess(
                    header_list.ordered_columns[0].width,
                    header_list.ordered_columns[1].width,
                )
                self.assertTrue(header_list.render_line(0).text.rstrip().endswith("…"))
                header_list.hover_coordinate = Coordinate(0, 1)
                await pilot.pause()
                self.assertEqual("long-header-key", header_list.tooltip)
                self.assertEqual(header_list.region.y, header_details.region.y)
                self.assertLess(header_list.region.x, header_details.region.x)
                await pilot.press("tab")
                self.assertIs(header_list, app.screen.focused)
                await pilot.press("tab")
                self.assertIs(
                    header_details.query_one(".record-content-scroll"), app.screen.focused
                )
                await pilot.pause()
                header_content = app.screen.query_one(
                    "#record-header-details .record-content", Static
                )
                self.assertEqual(focused_panel, header_content.styles.background.hex)

                tabs.focus()
                app.screen.query_one(TabbedContent).active = "json"
                await pilot.pause()
                json_content = app.screen.query_one(".record-json", Static)
                self.assertEqual(content_panel, json_content.styles.background.hex)
                json_scroll = app.screen.query_one(
                    "#json .record-detail-scroll", KaskadeScrollableContainer
                )
                await pilot.press("tab")
                self.assertIs(json_scroll, app.screen.focused)
                await pilot.pause()
                self.assertEqual(focused_panel, json_content.styles.background.hex)

                await pilot.press("escape")
                self.assertIs(records_table, app.screen.focused)

    async def test_record_metadata_ellipsizes_labels_on_tiny_screens(self):
        with patch("kaskade.consumer.app.ConsumerService") as consumer_service:
            configure_consumer_service(consumer_service.return_value)
            app = KaskadeConsumer(
                ConsumerSettings("orders", {}, Deserialization.STRING, Deserialization.STRING)
            )

            async with app.run_test(size=(24, 24)) as pilot:
                app.push_screen(
                    TopicScreen(
                        Record(
                            topic="orders",
                            partition=0,
                            offset=1,
                            key=b"key",
                            value=b"value",
                        )
                    )
                )
                await pilot.pause()

                total_size = app.screen.query_one("#record-total-size", MetadataCell)
                deserializer = app.screen.query_one(".record-deserializer", MetadataCell)
                self.assertTrue(total_size.render().plain.splitlines()[0].endswith("…"))
                self.assertEqual("Total Size", total_size.tooltip)
                self.assertEqual("DESERIALIZER", deserializer.render().plain.splitlines()[0])
                self.assertIsNone(deserializer.tooltip)

    async def test_topic_details_use_native_tabs_and_a_contextual_footer(self):
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})
            configurations = (
                TopicConfiguration("retention.ms", "604800000"),
                TopicConfiguration("cleanup.policy", "compact"),
            )

            async with app.run_test() as pilot:
                app.push_screen(DescribeTopicScreen(Topic(name="orders"), configurations))
                await pilot.pause()

                details = app.screen.query_one(".topic-details", Container)
                tabs = app.screen.query_one(TabbedContent)
                metadata = app.screen.query_one("#topic-metadata", Grid)
                partitions = app.screen.query_one("#partitions-table", DataTable)
                configuration_table = app.screen.query_one("#configurations-table", DataTable)
                detail_tables = list(app.screen.query(StretchyDataTable))
                self.assertEqual("partitions", tabs.active)
                self.assertEqual(app.current_theme.background, details.styles.background.hex)
                self.assertEqual(0, tabs.styles.background.a)
                self.assertEqual(7, metadata.styles.grid_size_columns)
                self.assertEqual(1, metadata.styles.grid_size_rows)
                self.assertEqual(7, len(metadata.query(".topic-metadata-cell")))
                self.assertTrue(
                    all(
                        cell.content_region.height == 2
                        for cell in metadata.query(".topic-metadata-cell")
                    )
                )
                self.assertEqual(
                    [
                        "Partitions [0]",
                        "Configurations [2]",
                        "Groups [0]",
                        "Group Offsets [0]",
                        "Group Members [0]",
                    ],
                    [tab.label_text for tab in app.screen.query(Tab)],
                )
                self.assertEqual(
                    "[primary]Topic Details[/primary] [[primary]orders[/primary]]",
                    details.border_title,
                )
                self.assertNotEqual("none", details.styles.border_top[0])
                self.assertEqual("", tabs.styles.border_top[0])
                self.assertEqual(5, len(app.screen.query(TabPane)))
                self.assertEqual(5, len(app.screen.query(DataTable)))
                self.assertEqual(5, len(detail_tables))
                self.assertTrue(all(not table.zebra_stripes for table in detail_tables))
                self.assertEqual(
                    ["Name", "Value"],
                    [column.label.plain for column in configuration_table.ordered_columns],
                )
                self.assertEqual(
                    [
                        ["cleanup.policy", "compact"],
                        ["retention.ms", "604800000"],
                    ],
                    [
                        [
                            str(configuration_table.get_cell_at(Coordinate(row, column)))
                            for column in range(2)
                        ]
                        for row in range(2)
                    ],
                )
                for table in detail_tables:
                    self.assertIsNone(table.border_title)
                    self.assertEqual("", table.styles.border_top[0])
                    self.assertEqual(0, table.styles.background.a)
                self.assertGreater(partitions.content_region.height, 0)
                self.assertFalse(partitions.show_horizontal_scrollbar)
                self.assertIsInstance(app.screen.query_one(Footer), Footer)

                await pilot.press("l")
                await pilot.pause()
                self.assertEqual("configurations", tabs.active)
                self.assertGreater(
                    configuration_table.ordered_columns[0].width,
                    configuration_table.ordered_columns[1].width,
                )
                await pilot.press("l")
                self.assertEqual("groups", tabs.active)
                await pilot.press("h")
                self.assertEqual("configurations", tabs.active)

    async def test_topic_details_metadata_wraps_on_narrow_screens(self):
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})

            async with app.run_test(size=(60, 30)) as pilot:
                app.push_screen(DescribeTopicScreen(Topic(name="orders"), ()))
                await pilot.pause()

                details = app.screen.query_one(".topic-details", Container)
                metadata = app.screen.query_one("#topic-metadata", Grid)
                cells = list(metadata.query(".topic-metadata-cell"))
                self.assertEqual(app.screen.content_region.width, details.region.width)
                self.assertEqual(4, metadata.styles.grid_size_columns)
                self.assertEqual(2, metadata.styles.grid_size_rows)
                self.assertTrue(all(cell.content_region.height == 2 for cell in cells))
                self.assertEqual(cells[0].region.y, cells[3].region.y)
                self.assertGreater(cells[4].region.y, cells[0].region.y)
                self.assertGreater(
                    app.screen.query_one("#partitions-table", DataTable).content_region.height,
                    0,
                )

    async def test_topic_details_metadata_uses_three_columns_on_compact_screens(self):
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})

            async with app.run_test(size=(48, 30)) as pilot:
                app.push_screen(DescribeTopicScreen(Topic(name="orders"), ()))
                await pilot.pause()

                metadata = app.screen.query_one("#topic-metadata", Grid)
                cells = list(metadata.query(".topic-metadata-cell"))
                partitions = app.screen.query_one("#topic-partitions", Static)
                self.assertTrue(app.screen.has_class("-compact"))
                self.assertEqual(3, metadata.styles.grid_size_columns)
                self.assertEqual(3, metadata.styles.grid_size_rows)
                self.assertTrue(all(cell.content_region.height == 2 for cell in cells))
                self.assertEqual(cells[0].region.y, cells[2].region.y)
                self.assertGreater(cells[3].region.y, cells[0].region.y)
                self.assertGreaterEqual(partitions.content_region.width, len("PARTITIONS"))
                self.assertIsNone(partitions.tooltip)

    async def test_topic_details_metadata_ellipsizes_labels_on_tiny_screens(self):
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})

            async with app.run_test(size=(36, 30)) as pilot:
                app.push_screen(DescribeTopicScreen(Topic(name="orders"), ()))
                await pilot.pause()

                partitions = app.screen.query_one("#topic-partitions", Static)
                self.assertLess(partitions.content_region.width, len("PARTITIONS"))
                self.assertTrue(partitions.render().plain.splitlines()[0].endswith("…"))
                self.assertEqual("Partitions", partitions.tooltip)

    async def test_topic_details_help_excludes_ctrl_c_from_selected_text_copy(self):
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
            app = KaskadeAdmin({})

            async with app.run_test() as pilot:
                app.push_screen(DescribeTopicScreen(Topic(name="orders"), ()))
                await pilot.pause()

                await pilot.press("?")

                self.assertIsInstance(app.screen, HelpScreen)
                copy_bindings = {
                    binding.description: binding.keys
                    for binding in app.screen.help_bindings
                    if binding.description.startswith("Copy")
                }
                selected_text_copy_display = SELECTED_TEXT_COPY_KEY_DISPLAY or "shift+^c"
                self.assertEqual(
                    (selected_text_copy_display,),
                    copy_bindings["Copy Selected Text"],
                )
                self.assertEqual(("y",), copy_bindings["Copy Selection"])
                self.assertNotIn(
                    "ctrl+c",
                    {key for keys in copy_bindings.values() for key in keys},
                )

    async def test_chunk_size_uses_an_option_list_with_the_current_value_selected(self):
        with patch("kaskade.admin.app.TopicService") as topic_service:
            configure_admin_service(topic_service.return_value, {})
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
            with (
                self.subTest(theme=theme),
                patch("kaskade.admin.app.TopicService") as topic_service,
            ):
                configure_admin_service(topic_service.return_value, {})
                app = KaskadeAdmin({})
                app.theme = theme

                async with app.run_test(size=(80, 24)):
                    screenshot = app.export_screenshot()

                self.assertIn("<svg", screenshot)
