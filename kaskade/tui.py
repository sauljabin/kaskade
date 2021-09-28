from pyfiglet import Figlet
from rich import box
from rich.panel import Panel
from rich.text import Text
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
        await self.view.dock(Header(), edge="top")
        await self.view.dock(Footer(), edge="bottom")
        await self.view.dock(Topics(self.kafka), edge="left", size=50)
        await self.view.dock(Data(), edge="right")

    async def on_load(self, event):
        await self.bind("q", "quit")


class Footer(Widget):
    name = "Footer"

    def __init__(self):
        super().__init__(name=self.name)
        self.layout_size = 1

    def render(self):
        text = Text(justify="right")
        text.append(kaskade_package.name, style="bold magenta")
        text.append(" v{}".format(kaskade_package.version), style="green")
        return text


class Header(Widget):
    name = "Header"

    def __init__(self):
        super().__init__(name=self.name)
        self.layout_size = 6

    def render(self):
        figlet = Figlet(font="slant")
        text = Text()
        text.append(figlet.renderText(kaskade_package.name), style="magenta")
        return text


class Topics(Widget):
    mouse_over = Reactive(False)
    has_focus = Reactive(False)
    name = "Topics"

    def __init__(self, kafka):
        super().__init__(name=self.name)
        self.kafka = kafka

    def render(self):
        topics = sorted(self.kafka.topics())
        content = "\n".join([topic for topic in topics])
        return Panel(
            content,
            title=self.name,
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


class Data(Widget):
    mouse_over = Reactive(False)
    has_focus = Reactive(False)
    name = "Data"

    def __init__(self):
        super().__init__(name=self.name)

    def render(self):
        return Panel(
            "Hello World!",
            title=self.name,
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
