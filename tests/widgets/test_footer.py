from unittest import TestCase

from kaskade.renderables.kaskade_version import KaskadeVersion
from kaskade.widgets.footer import Footer


class TestFooter(TestCase):
    def test_size(self):
        footer = Footer()

        footer.on_mount()

        self.assertEqual(1, footer.layout_size)

    def test_render(self):
        footer = Footer()

        actual = footer.render()

        self.assertIsInstance(actual.renderables[0], KaskadeVersion)
