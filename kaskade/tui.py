from typing import Optional, Type

from rich.console import Console
from textual.app import App
from textual.driver import Driver
from textual.keys import Keys
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade.config import Config
from kaskade.kafka.cluster_service import ClusterService
from kaskade.kafka.models import Topic
from kaskade.kafka.topic_service import TopicService
from kaskade.utils.circular_list import CircularList
from kaskade.widgets.footer import Footer
from kaskade.widgets.header import Header
from kaskade.widgets.help import Help
from kaskade.widgets.topic_detail import TopicDetail
from kaskade.widgets.topic_header import TopicHeader
from kaskade.widgets.topic_list import TopicList


class Tui(App):
    __topic: Optional[Topic] = None
    show_help = Reactive(False)

    def __init__(
        self,
        config: Config,
        console: Optional[Console] = None,
        screen: bool = True,
        driver_class: Optional[Type[Driver]] = None,
        log: str = "",
        log_verbosity: int = 1,
    ) -> None:
        super().__init__(
            console=console,
            screen=screen,
            driver_class=driver_class,
            log=log,
            log_verbosity=log_verbosity,
        )
        self.config = config

        self.topic_service = TopicService(self.config)
        self.cluster_service = ClusterService(self.config)

        self.cluster = self.cluster_service.cluster()
        self.topics = self.topic_service.topics()

        self.footer = Footer()
        self.header = Header()
        self.help = Help()

        self.topic_list = TopicList()
        self.topic_detail = TopicDetail()
        self.topic_header = TopicHeader()
        self.focusables = CircularList(
            [self.topic_list, self.topic_header, self.topic_detail]
        )

    async def on_mount(self) -> None:
        self.help.layout_offset_x = -30
        await self.view.dock(self.header, edge="top")
        await self.view.dock(self.footer, edge="bottom")
        await self.view.dock(self.topic_list, edge="left", size=40)
        await self.view.dock(self.topic_header, self.topic_detail, edge="top")
        await self.view.dock(self.help, edge="left", size=30, z=1)

    async def on_load(self) -> None:
        await self.bind("q", "quit")
        await self.bind("Q", "quit")
        await self.bind("?", "toggle_help")
        await self.bind(Keys.Escape, "default_view")
        await self.bind(Keys.F5, "reload_content")
        await self.bind(Keys.Left, "change_focus('{}')".format(Keys.Left))
        await self.bind(Keys.Right, "change_focus('{}')".format(Keys.Right))

    async def watch_show_help(self, show_help: bool) -> None:
        if show_help:
            self.help.layout_offset_x = self.view.size.width - 30
        else:
            self.help.layout_offset_x = -30

    async def action_toggle_help(self) -> None:
        self.show_help = not self.show_help
        if self.show_help:
            await self.set_focus(self.help)
            self.focusables.reset()

    async def action_default_view(self) -> None:
        self.show_help = False

    async def action_reload_content(self) -> None:
        self.topics = self.topic_service.topics()
        self.topic = None
        self.focusables.reset()
        self.topic_list.scrollable_list = None
        self.topic_detail.table = None
        self.topic_list.refresh()
        self.topic_header.refresh()
        self.topic_detail.refresh()
        await self.set_focus(None)

    @property
    def topic(self) -> Optional[Topic]:
        return self.__topic

    @topic.setter
    def topic(self, topic: Optional[Topic]) -> None:
        self.__topic = topic
        self.topic_detail.table = None
        self.topic_detail.tabs.index = 0
        self.topic_detail.refresh()
        self.topic_header.refresh()

    async def action_change_focus(self, key: Keys) -> None:
        focused: Widget = (
            self.focusables.next() if Keys.Right == key else self.focusables.previous()
        )
        await focused.focus()
