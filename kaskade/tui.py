from textual.app import App

from kaskade import kaskade_package
from kaskade.body import Data
from kaskade.footer import Footer
from kaskade.header import Header
from kaskade.kafka import Kafka
from kaskade.sidebar import Topics


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
            title=kaskade_package.name,
        )
        self.config = config
        self.kafka = Kafka(self.config.kafka)

    async def on_mount(self):
        await self.view.dock(Header(), edge="top")
        await self.view.dock(Footer(), edge="bottom")
        await self.view.dock(Topics(self.kafka), edge="left", size=50)
        await self.view.dock(Data(), edge="right")

    async def on_load(self, event):
        await self.bind("q", "quit")
