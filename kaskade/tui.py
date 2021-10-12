from typing import Optional, Type

from rich.console import Console
from textual.app import App
from textual.driver import Driver
from textual.keys import Keys
from textual.widget import Widget

from kaskade.config import Config
from kaskade.kafka.cluster import ClusterService
from kaskade.kafka.topic import TopicService
from kaskade.utils.circular_list import CircularList
from kaskade.widgets.body import Body
from kaskade.widgets.footer import Footer
from kaskade.widgets.header import Header
from kaskade.widgets.sidebar import Sidebar


class Tui(App):
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
        self.topic = None

        self.sidebar = Sidebar()
        self.body = Body()
        self.footer = Footer()
        self.header = Header()
        self.focusables = CircularList([self.sidebar, self.body])

    async def on_mount(self) -> None:
        await self.view.dock(self.header, edge="top")
        await self.view.dock(self.footer, edge="bottom")
        await self.view.dock(self.sidebar, edge="left", size=40)
        await self.view.dock(self.body, edge="right")

    async def on_load(self) -> None:
        await self.bind("q", "quit")
        await self.bind(Keys.F5, "reload_content")
        await self.bind(Keys.Left, "change_focus('{}')".format(Keys.Left))
        await self.bind(Keys.Right, "change_focus('{}')".format(Keys.Right))

    async def action_reload_content(self) -> None:
        self.topics = self.topic_service.topics()
        self.topic = None
        self.focusables.reset()
        self.sidebar.scrollable_list = None
        self.body.partitions_table = None
        await self.set_focus(None)

    async def action_change_focus(self, key: Keys) -> None:
        focused: Widget = (
            self.focusables.next() if Keys.Right else self.focusables.previous()
        )
        print(focused)
        await focused.focus()
