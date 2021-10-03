from unittest import TestCase
from unittest.mock import patch

from kaskade.kaskade import Kaskade
from tests import faker


class TestKaskade(TestCase):
    @patch("kaskade.kaskade.pkg_resources")
    def test_default_values(self, mock_pkg_resources):
        expected_value = faker.bothify("#.#.#-alpha")
        mock_pkg_resources.get_distribution.return_value.version = expected_value

        kaskade = Kaskade()

        self.assertEqual("kaskade", kaskade.name)
        self.assertEqual(expected_value, kaskade.version)
