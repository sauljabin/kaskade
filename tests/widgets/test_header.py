from unittest import TestCase
from unittest.mock import PropertyMock, patch

from rich.columns import Columns

from kaskade.renderables.cluster_info import ClusterInfo
from kaskade.renderables.kaskade_name import KaskadeName
from kaskade.renderables.shortcuts_header import ShortcutsHeader
from kaskade.widgets.header import Header


class TestHeader(TestCase):
    @patch("kaskade.widgets.header.Header.app", new_callable=PropertyMock)
    def test_size(self, mock_app):
        header = Header()

        header.on_mount()

        self.assertEqual(6, header.layout_size)

    @patch("kaskade.widgets.header.Header.app", new_callable=PropertyMock)
    def test_renderables(self, mock_app):
        header = Header()

        header.on_mount()
        actual = header.render()

        self.assertEqual(3, actual.padding)
        self.assertIsInstance(actual, Columns)
        self.assertIsInstance(actual.renderables[0], KaskadeName)
        self.assertIsInstance(actual.renderables[1], ClusterInfo)
        self.assertIsInstance(actual.renderables[2], ShortcutsHeader)
