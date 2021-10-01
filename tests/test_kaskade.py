from unittest import TestCase
from unittest.mock import patch

from pyfiglet import Figlet

from kaskade.kaskade import Kaskade
from tests import faker


class TestKaskade(TestCase):
    @patch("kaskade.kaskade.pkg_resources")
    def test_default_values(self, mock_pkg_resources):
        expected_value = faker.bothify("#.#.#-alpha")
        mock_pkg_resources.get_distribution.return_value.version = expected_value

        kaskade = Kaskade()

        self.assertEqual("kaskade", kaskade.name)
        self.assertEqual("https://github.com/sauljabin/kaskade", kaskade.documentation)
        self.assertEqual(expected_value, kaskade.version)

    def test_figlet_name(self):
        figlet = Figlet(font="standard")

        kaskade = Kaskade()

        self.assertIn(kaskade.figleted_name(), figlet.renderText("kaskade"))

    @patch("kaskade.kaskade.pkg_resources")
    def test_riched_version(self, mock_pkg_resources):
        expected_version = faker.bothify("#.#.#")
        mock_pkg_resources.get_distribution.return_value.version = expected_version
        expected_value = (
            "kaskade v" + expected_version + " https://github.com/sauljabin/kaskade"
        )

        kaskade = Kaskade()

        self.assertIn(kaskade.riched_version().plain, expected_value)

    def test_riched_name(self):
        figlet = Figlet(font="standard")

        kaskade = Kaskade()

        self.assertIn(kaskade.riched_name().plain, figlet.renderText("kaskade"))
