import unittest
from unittest.mock import MagicMock, call, patch

from faker import Faker

from kaskade.cli import Cli

faker = Faker()


class TestCli(unittest.TestCase):
    def test_options_to_attributes(self):
        dict_fake = faker.pydict(2)
        dict_fake["test"] = None

        cli = Cli(dict_fake)

        for key, value in dict_fake.items():
            self.assertEqual(getattr(cli, key), value)

        self.assertEqual(cli.test, None)

    @patch("kaskade.cli.sys")
    @patch("kaskade.cli.kaskade_package")
    @patch("kaskade.cli.Console")
    def test_print_version_option(
        self, mock_class_console, mock_kaskade_package, mock_sys
    ):
        mock_kaskade_package.version = faker.text()
        mock_kaskade_package.documentation = faker.text()
        mock_console = MagicMock()
        mock_class_console.return_value = mock_console
        cli = Cli({"version": True})

        cli.run()

        calls = [
            call("Version: {}".format(mock_kaskade_package.version)),
            call("Doc: {}".format(mock_kaskade_package.documentation)),
        ]
        mock_console.print.assert_has_calls(calls)
        self.assertEqual(cli.version, True)
