from unittest import TestCase
from unittest.mock import ANY, MagicMock, call, patch

from kaskade.renderables.shortcuts import Shortcuts
from tests import faker


class TestShortcuts(TestCase):
    @patch("kaskade.renderables.shortcuts.Table")
    def test_render_shortcuts_in_a_table(self, mock_class_table):
        mock_table = MagicMock()
        mock_class_table.return_value = mock_table

        shortcuts = Shortcuts()
        shortcuts.shortcuts = faker.pydict(
            nb_elements=10, variable_nb_elements=False, value_types=str
        )
        actual = shortcuts.__rich__()

        self.assertEqual(mock_table, actual)
        mock_class_table.assert_called_with(box=None, expand=False)
        mock_table.add_column.assert_has_calls(
            [call(style="magenta bold"), call(style="yellow bold")]
        )

        mock_table.add_row.assert_has_calls(
            [
                call(ANY, ANY, ANY, ANY, ANY, ANY),
                call(ANY, ANY, ANY, ANY, ANY, ANY),
                call(ANY, ANY, ANY, ANY),
            ]
        )

    @patch("kaskade.renderables.shortcuts.Table")
    def test_render_shortcuts_in_a_table_multiple_of_4(self, mock_class_table):
        mock_table = MagicMock()
        mock_class_table.return_value = mock_table

        shortcuts = Shortcuts()
        shortcuts.shortcuts = faker.pydict(
            nb_elements=12, variable_nb_elements=False, value_types=str
        )
        actual = shortcuts.__rich__()

        self.assertEqual(mock_table, actual)
        mock_class_table.assert_called_with(box=None, expand=False)
        mock_table.add_column.assert_has_calls(
            [call(style="magenta bold"), call(style="yellow bold")]
        )

        last = [cell for cell in list(shortcuts.shortcuts.items())[-1]]
        last[0] = last[0] + ":"

        mock_table.add_row.assert_has_calls(
            [
                call(ANY, ANY, ANY, ANY, ANY, ANY),
                call(ANY, ANY, ANY, ANY, ANY, ANY),
                call(ANY, ANY, ANY, ANY, *last),
            ]
        )

    @patch("kaskade.renderables.shortcuts.Table")
    def test_render_shortcuts_in_a_table_9(self, mock_class_table):
        mock_table = MagicMock()
        mock_class_table.return_value = mock_table

        shortcuts = Shortcuts()
        shortcuts.shortcuts = faker.pydict(
            nb_elements=9, variable_nb_elements=False, value_types=str
        )
        actual = shortcuts.__rich__()

        self.assertEqual(mock_table, actual)
        mock_class_table.assert_called_with(box=None, expand=False)
        mock_table.add_column.assert_has_calls(
            [call(style="magenta bold"), call(style="yellow bold")]
        )

        mock_table.add_row.assert_has_calls(
            [
                call(ANY, ANY, ANY, ANY, ANY, ANY),
                call(ANY, ANY, ANY, ANY),
                call(ANY, ANY, ANY, ANY),
            ]
        )

    def test_string(self):
        shortcuts = Shortcuts()
        shortcuts.shortcuts = faker.pydict(
            nb_elements=10, variable_nb_elements=False, value_types=str
        )
        actual = str(shortcuts)

        self.assertEqual(str(shortcuts.shortcuts), actual)
