from unittest import TestCase
from unittest.mock import MagicMock, call, patch

from kaskade.renderables.shortcuts import Shortcuts


class TestShortcuts(TestCase):
    @patch("kaskade.renderables.shortcuts.Table")
    def test_render_shortcuts_in_a_table(self, mock_class_table):
        mock_table = MagicMock()
        mock_class_table.return_value = mock_table

        shortcuts = Shortcuts()
        actual = shortcuts.__rich__()

        self.assertEqual(mock_table, actual)
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
