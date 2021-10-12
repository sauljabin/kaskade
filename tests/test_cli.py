import unittest
from unittest.mock import MagicMock, call, patch

from kaskade.cli import Cli
from tests import faker


class TestCli(unittest.TestCase):
    @patch("kaskade.cli.KaskadeVersion")
    @patch("kaskade.cli.KaskadeName")
    @patch("kaskade.cli.Console")
    def test_print_version_option(
        self, mock_class_console, mock_class_kaskade_name, mock_class_kaskade_version
    ):
        mock_console = MagicMock()
        mock_class_console.return_value = mock_console
        cli = Cli(print_version=True, config_file="")

        with self.assertRaises(SystemExit):
            cli.run()

        calls = [
            call(mock_class_kaskade_name.return_value),
            call(mock_class_kaskade_version.return_value),
        ]
        mock_console.print.assert_has_calls(calls)

    @patch("kaskade.cli.Config")
    @patch("kaskade.cli.Tui")
    def test_run_tui(self, mock_class_tui, mock_class_config):
        random_path = faker.file_path(extension="yml")
        cli = Cli(print_version=False, config_file=random_path)
        cli.run()
        mock_class_tui.run.assert_called_once_with(
            config=mock_class_config.return_value
        )
        mock_class_config.assert_called_once_with(random_path)

    @patch("kaskade.cli.Console")
    def test_print_exception(self, mock_class_console):
        random_path = faker.file_path(extension="yml")
        random_message = faker.text()
        cli = Cli(print_version=False, config_file=random_path)
        cli.run_tui = MagicMock(side_effect=Exception(random_message))
        cli.run()
        mock_class_console.return_value.print.assert_called_once_with(
            ":thinking_face: [bold red]A problem has occurred[/]: {}".format(
                random_message
            )
        )
