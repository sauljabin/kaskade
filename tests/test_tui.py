import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, call, patch

from textual.keys import Keys

from kaskade.tui import Tui


class TestTui(IsolatedAsyncioTestCase):
    @classmethod
    def tearDownClass(cls):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    @patch("kaskade.tui.TopicService")
    @patch("kaskade.tui.ClusterService")
    async def test_bind_on_load(
        self, mock_cluster_service_class, mock_topic_service_class
    ):
        tui = Tui()
        tui.bind = AsyncMock()

        calls = [
            call("q", "quit"),
            call(Keys.F5, "reload_content"),
            call(Keys.Left, "change_focus('{}')".format(Keys.Left)),
            call(Keys.Right, "change_focus('{}')".format(Keys.Right)),
        ]

        await tui.on_load()

        tui.bind.assert_has_calls(calls)

    @patch("kaskade.tui.TopicService")
    @patch("kaskade.tui.ClusterService")
    @patch("kaskade.tui.Tui.view", new_callable=AsyncMock)
    async def test_on_mount(
        self, mock_view, mock_cluster_service_class, mock_topic_service_class
    ):
        tui = Tui()

        calls = [
            call(tui.header, edge="top"),
            call(tui.footer, edge="bottom"),
            call(tui.sidebar, edge="left", size=40),
            call(tui.body, edge="right"),
        ]

        await tui.on_mount()

        mock_view.dock.assert_has_calls(calls)

    @patch("kaskade.tui.TopicService")
    @patch("kaskade.tui.ClusterService")
    async def test_reload(self, mock_cluster_service_class, mock_topic_service_class):
        tui = Tui()
        tui.set_focus = AsyncMock()
        tui.focusables = Mock()

        await tui.action_reload_content()

        self.assertEqual(
            mock_topic_service_class.return_value.topics.return_value, tui.topics
        )
        self.assertIsNone(tui.topic)
        self.assertIsNone(tui.sidebar.scrollable_list)
        self.assertIsNone(tui.body.partitions_table)
        tui.set_focus.assert_called_once_with(None)
        tui.focusables.reset.assert_called_once()

    @patch("kaskade.tui.TopicService")
    @patch("kaskade.tui.ClusterService")
    def test_circular_list(self, mock_cluster_service_class, mock_topic_service_class):
        tui = Tui()

        self.assertEqual([tui.sidebar, tui.body], tui.focusables.list)

    @patch("kaskade.tui.TopicService")
    @patch("kaskade.tui.ClusterService")
    async def test_change_focus(
        self, mock_cluster_service_class, mock_topic_service_class
    ):
        tui = Tui()
        mock_next_focusable = AsyncMock()
        mock_previous_focusable = AsyncMock()
        mock_next = Mock(return_value=mock_next_focusable)
        mock_previous = Mock(return_value=mock_previous_focusable)
        tui.focusables = Mock()
        tui.focusables.next = mock_next
        tui.focusables.previous = mock_previous

        await tui.action_change_focus(Keys.Right)
        mock_next_focusable.focus.assert_called_once()

        await tui.action_change_focus(Keys.Left)
        mock_previous_focusable.focus.assert_called_once()
