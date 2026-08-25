import unittest

from textual.theme import BUILTIN_THEMES

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
