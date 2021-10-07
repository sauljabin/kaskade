from textual.app import App
from textual.keys import Keys

from kaskade.kafka import Kafka
from kaskade.utils.circular_list import CircularList
from kaskade.widgets.body import Body
from kaskade.widgets.footer import Footer
from kaskade.widgets.header import Header
from kaskade.widgets.sidebar import Sidebar


class Tui(App):
    def __init__(
        self,
        console=None,
        screen=True,
        driver_class=None,
        log="",
        log_verbosity=1,
        config=None,
    ):
        super().__init__(
            console=console,
            screen=screen,
            driver_class=driver_class,
            log=log,
            log_verbosity=log_verbosity,
        )
        self.config = config
        self.kafka = Kafka(self.config)
        self.topics = self.kafka.topics()
        self.topic = None

        self.sidebar = Sidebar()
        self.body = Body()
        self.footer = Footer()
        self.header = Header()
        self.focusables = CircularList([self.sidebar, self.body])

    async def on_mount(self):
        await self.view.dock(self.header, edge="top")
        await self.view.dock(self.footer, edge="bottom")
        await self.view.dock(self.sidebar, edge="left", size=40)
        await self.view.dock(self.body, edge="right")

    async def on_load(self):
        await self.bind("q", "quit")
        await self.bind(Keys.F5, "reload_content")

        await self.bind(Keys.Left, "change_focus('{}')".format(Keys.Left))
        await self.bind(Keys.Right, "change_focus('{}')".format(Keys.Right))

    async def action_reload_content(self):
        self.topics = self.kafka.topics()
        self.topic = None
        self.focusables.reset()
        self.sidebar.scrollable_list = None
        self.body.partitions_table = None
        await self.set_focus(None)

    async def action_change_focus(self, key):
        if key == Keys.Right:
            focused = self.focusables.next()
        else:
            focused = self.focusables.previous()

        if focused:
            await focused.focus()
