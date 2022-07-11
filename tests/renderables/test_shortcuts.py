from unittest import TestCase
from unittest.mock import MagicMock, call, patch

from kaskade.renderables.shortcuts import Shortcuts
from tests import faker


class TestShortcuts(TestCase):
    def test_string(self):
        random_dict = faker.pydict()
        expected = str(random_dict)
        shortcuts = Shortcuts()
        shortcuts.shortcuts = random_dict
        actual = str(shortcuts)

        self.assertEqual(expected, actual)

    @patch("kaskade.renderables.shortcuts.Table")
    def test_render_shortcuts_in_a_table(self, mock_class_table):
        mock_table = MagicMock()
        mock_class_table.return_value = mock_table

        random_dict = {"test": faker.pydict()}
        shortcuts = Shortcuts()
        shortcuts.shortcuts = random_dict

        actual = shortcuts.__rich__()

        self.assertEqual(mock_table, actual)
        mock_class_table.assert_called_with(
            box=None, expand=False, show_footer=False, show_header=False
        )
        mock_table.add_column.assert_has_calls(
            [call(style="magenta bold"), call(style="yellow bold")]
        )
        calls = []
        for category, shortcuts in random_dict.items():
            calls.append(call("[blue bold]test[/]"))
            for action, shortcut in shortcuts.items():
                calls.append(call("{}".format(action), str(shortcut)))
            else:
                calls.append(call())

        mock_table.add_row.assert_has_calls(calls)
