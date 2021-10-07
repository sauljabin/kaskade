from unittest import TestCase

from pyfiglet import Figlet

from kaskade.renderables.kaskade_name import KaskadeName


class TestKaskadeName(TestCase):
    def test_rich_name(self):
        figlet = Figlet(font="standard")
        expected = figlet.renderText("kaskade")

        rich = KaskadeName().__rich__()
        actual = rich.plain

        self.assertIn(actual, expected)

    def test_name(self):
        figlet = Figlet(font="standard")
        expected = figlet.renderText("kaskade").rstrip()

        actual = str(KaskadeName())

        self.assertEqual(expected, actual)
