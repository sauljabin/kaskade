from unittest import TestCase
from unittest.mock import patch

from kaskade.kaskade import Kaskade
from tests import faker


class TestKaskade(TestCase):
    @patch("kaskade.kaskade.pkg_resources")
    def test_figleted_name(self, mock_pkg_resources):
        mock_pkg_resources.get_distribution.return_value.version = faker.bothify(
            "#.#.#-alpha"
        )

        kaskade = Kaskade()

        self.assertEqual(kaskade.name, "kaskade")
        self.assertEqual(kaskade.documentation, "https://github.com/sauljabin/kaskade")
        self.assertEqual(
            kaskade.version, mock_pkg_resources.get_distribution.return_value.version
        )
