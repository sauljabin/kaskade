from unittest import TestCase
from unittest.mock import MagicMock, call, patch

from pyfiglet import Figlet
from rich.text import Text

from kaskade.renderables.kaskade_name import KaskadeName
from kaskade.renderables.kaskade_version import KaskadeVersion
from kaskade.renderables.shortcuts import Shortcuts
from tests import faker

version = faker.bothify("#.#.#")


class TestKaskadeVersion(TestCase):
    @patch("kaskade.renderables.kaskade_version.VERSION", version)
    def test_version(self):
        expected_value = "kaskade v" + version

        actual = str(KaskadeVersion())

        self.assertEqual(expected_value, actual)

    @patch("kaskade.renderables.kaskade_version.VERSION", version)
    def test_rich_version(self):
        expected_value = "kaskade v" + version

        rich = KaskadeVersion().__rich__()
        actual = rich.plain

        self.assertIsInstance(rich, Text)
        self.assertEqual(expected_value, actual)


class TestKaskadeName(TestCase):
    def test_rich_name(self):
        figlet = Figlet(font="standard")
        expected = figlet.renderText("kaskade")

        rich = KaskadeName().__rich__()
        actual = rich.plain

        self.assertIn(actual, expected)

    def test_name(self):
        figlet = Figlet(font="standard")
        expected = figlet.renderText("kaskade").rstrip()

        actual = str(KaskadeName())

        self.assertEqual(expected, actual)


class TestShortcuts(TestCase):
    @patch("kaskade.renderables.shortcuts.Table")
    def test_render_shortcuts_in_a_table(self, mock_class_table):
        mock_table = MagicMock()
        mock_class_table.return_value = mock_table

        shortcuts = Shortcuts()
        shortcuts.__rich__()

        mock_class_table.assert_called_with(box=None, expand=False)
        mock_table.add_column.assert_has_calls(
            [call(style="magenta bold"), call(style="yellow bold")]
        )

        mock_table.add_row.assert_has_calls(
            [
                call("quit:", "q"),
                call("refresh:", "f5"),
                call("navigate:", "\u2190 \u2192 \u2191 \u2193"),
            ]
        )

    def test_string(self):
        expected = str(
            {
                "quit": "q",
                "refresh": "f5",
                "navigate": "\u2190 \u2192 \u2191 \u2193",
            }
        )
        actual = str(Shortcuts())

        self.assertEqual(expected, actual)
