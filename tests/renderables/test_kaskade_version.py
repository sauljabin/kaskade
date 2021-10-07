from unittest import TestCase
from unittest.mock import patch

from rich.text import Text

from kaskade.renderables.kaskade_version import KaskadeVersion
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
