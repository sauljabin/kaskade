from rich import box
from rich.panel import Panel
from textual.app import App
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade import kaskade_package
from kaskade.kafka import Kafka


class Kaskade(App):
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
        self.kafka = Kafka(self.config)

    async def on_mount(self):
        await self.view.dock(Topics(self.kafka), edge="left", size=50)

    async def on_load(self, event):
        await self.bind("q", "quit")


class Topics(Widget):
    mouse_over = Reactive(False)
    has_focus = Reactive(False)
    title = "Topics"

    def __init__(self,kafka):
        super().__init__(name=self.title)
        self.kafka = kafka

    def render(self):
        topics = sorted(self.kafka.topics())
        content = "\n".join([topic for topic in topics])
        return Panel(content,
            title=self.title,
            border_style=self.border_style(),
            box=box.SQUARE,
            title_align="left",
        )

    def border_style(self):
        return "green" if self.mouse_over or self.has_focus else "grey93"

    async def on_enter(self):
        self.mouse_over = True

    async def on_leave(self):
        self.mouse_over = False

    async def on_focus(self, event):
        self.has_focus = True

    async def on_blur(self, event):
        self.has_focus = False
