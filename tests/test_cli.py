import unittest
from unittest.mock import MagicMock, call, patch

from kaskade.cli import Cli
from tests import faker


class TestCli(unittest.TestCase):
    @patch("kaskade.cli.kaskade_package")
    @patch("kaskade.cli.Console")
    def test_print_version_option(self, mock_class_console, mock_kaskade_package):
        mock_kaskade_package.version = faker.text()
        mock_kaskade_package.name = faker.text()
        mock_kaskade_package.documentation = faker.text()
        mock_console = MagicMock()
        mock_class_console.return_value = mock_console
        cli = Cli(print_version=True)

        with self.assertRaises(SystemExit):
            cli.run()

        calls = [
            call(
                "[magenta]{}[/] [green]v{}[/]".format(
                    mock_kaskade_package.name, mock_kaskade_package.version
                )
            ),
            call("{}".format(mock_kaskade_package.documentation)),
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
