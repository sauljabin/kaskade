import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, call, patch

from textual.keys import Keys

from kaskade.tui import Tui
from kaskade.utils.circular_list import CircularList


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
        tui = Tui(config=MagicMock())
        tui.bind = AsyncMock()

        calls = [
            call(Keys.ControlC, "quit"),
            call(Keys.ControlR, "toggle_consumer_mode"),
            call(Keys.ControlD, "toggle_describer_mode"),
            call("?", "toggle_help"),
            call(Keys.Escape, "back"),
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
        tui = Tui(config=MagicMock())

        calls = [
            call(tui.header_widget, edge="top"),
            call(tui.footer_widget, edge="bottom"),
            call(tui.topic_list_widget, edge="left", size=40),
            call(
                tui.topic_header_widget,
                tui.describer_mode_widget,
                tui.consumer_mode_widget,
                edge="top",
                size=1000,
            ),
        ]

        await tui.on_mount()

        mock_view.dock.assert_has_calls(calls)

    @patch("kaskade.tui.TopicService")
    @patch("kaskade.tui.ClusterService")
    def test_focusables_list(
        self, mock_cluster_service_class, mock_topic_service_class
    ):
        tui = Tui(config=MagicMock())

        self.assertEqual(
            [
                tui.topic_list_widget,
                tui.describer_mode_widget,
                tui.consumer_mode_widget,
            ],
            tui.focusables.list,
        )

    @patch("kaskade.tui.TopicService")
    @patch("kaskade.tui.ClusterService")
    async def test_change_focus_next(
        self, mock_cluster_service_class, mock_topic_service_class
    ):
        tui = Tui(config=MagicMock())

        mock_next_focusable = AsyncMock()
        mock_previous_focusable = AsyncMock()

        tui.focusables = CircularList([mock_next_focusable, mock_previous_focusable])

        await tui.action_change_focus(Keys.Right)
        mock_next_focusable.focus.assert_called_once()

    @patch("kaskade.tui.TopicService")
    @patch("kaskade.tui.ClusterService")
    async def test_change_focus_previous(
        self, mock_cluster_service_class, mock_topic_service_class
    ):
        tui = Tui(config=MagicMock())

        mock_next_focusable = AsyncMock()
        mock_previous_focusable = AsyncMock()

        tui.focusables = CircularList([mock_next_focusable, mock_previous_focusable])

        await tui.action_change_focus(Keys.Left)
        mock_previous_focusable.focus.assert_called_once()
