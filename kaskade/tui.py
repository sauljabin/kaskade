from threading import Event, Thread
from typing import Any, Optional, Type

from confluent_kafka import KafkaException
from rich.console import Console
from textual.app import App
from textual.driver import Driver
from textual.keys import Keys
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade import logger
from kaskade.config import Config
from kaskade.kafka.cluster_service import ClusterService
from kaskade.kafka.models import Topic
from kaskade.kafka.topic_service import TopicService
from kaskade.utils.circular_list import CircularList
from kaskade.widgets.consumer_mode import ConsumerMode
from kaskade.widgets.describer_mode import DescriberMode
from kaskade.widgets.error import Error
from kaskade.widgets.footer import Footer
from kaskade.widgets.header import Header
from kaskade.widgets.help import Help
from kaskade.widgets.topic_header import TopicHeader
from kaskade.widgets.topic_list import TopicList


class Tui(App):
    __topic: Optional[Topic] = None
    show_help = Reactive(False)
    error = Reactive("")
    background_lock: Optional[Event] = None

    def __init__(
        self,
        config: Config,
        console: Optional[Console] = None,
        screen: bool = True,
        driver_class: Optional[Type[Driver]] = None,
        log_verbosity: int = 1,
    ) -> None:
        super().__init__(
            console=console,
            screen=screen,
            driver_class=driver_class,
            log_verbosity=log_verbosity,
        )
        self.config = config

        self.topic_service = TopicService(self.config)
        self.cluster_service = ClusterService(self.config)

        self.cluster = self.cluster_service.current()
        self.topics = self.topic_service.list()

        self.footer_widget = Footer()
        self.header_widget = Header()

        self.help_widget = Help()
        self.error_widget = Error()

        self.topic_list_widget = TopicList()
        self.topic_header_widget = TopicHeader()

        self.describer_mode_widget = DescriberMode()
        self.consumer_mode_widget = ConsumerMode()

        self.focusables = CircularList(
            [
                self.topic_list_widget,
                self.describer_mode_widget,
                self.consumer_mode_widget,
            ]
        )

    def background_execution(self, refresh_rate: float) -> None:
        self.background_lock = Event()
        while self.is_running and not self.background_lock.wait(refresh_rate):
            logger.debug("Background thread is running")
            self.reload_content()
        logger.debug("Closing background thread")

    def log(self, *args: Any, verbosity: int = 1, **kwargs: Any) -> None:
        if verbosity > self.log_verbosity:
            return

        message = " ".join(str(arg) for arg in args)
        if kwargs:
            key_values = " ".join(f"{key}={value}" for key, value in kwargs.items())
            message = " ".join((message, key_values))

        logger.debug(message)

    async def on_mount(self) -> None:
        self.help_widget.visible = False
        self.error_widget.visible = False
        self.consumer_mode_widget.visible = False

        await self.view.dock(self.header_widget, edge="top")
        await self.view.dock(self.footer_widget, edge="bottom")
        await self.view.dock(self.topic_list_widget, edge="left", size=40)
        await self.view.dock(
            self.topic_header_widget,
            self.describer_mode_widget,
            self.consumer_mode_widget,
            edge="top",
            size=1000,
        )
        await self.view.dock(self.error_widget, edge="right", size=40, z=1)
        await self.view.dock(self.help_widget, edge="right", size=30, z=1)

        refresh = (
            True
            if self.config.kaskade.get("refresh") is None
            else self.config.kaskade.get("refresh")
        )

        if refresh:
            refresh_rate = (
                5
                if self.config.kaskade.get("refresh-rate") is None
                else self.config.kaskade.get("refresh-rate")
            )

            logger.debug("Refresh enable with %.1f secs", refresh_rate)
            background_thread = Thread(
                target=self.background_execution, args=(refresh_rate,)
            )
            background_thread.start()
            self.set_interval(refresh_rate, self.topic_list_widget.refresh)
            self.set_interval(refresh_rate, self.topic_header_widget.refresh)
            self.set_interval(refresh_rate, self.describer_mode_widget.refresh)
        else:
            logger.debug("Auto-refresh disabled")

    async def on_load(self) -> None:
        await self.bind(Keys.ControlC, "quit")
        await self.bind(Keys.ControlR, "toggle_consumer_mode")
        await self.bind(Keys.ControlD, "toggle_describer_mode")
        await self.bind("?", "toggle_help")
        await self.bind(Keys.Escape, "back")
        await self.bind(Keys.F5, "reload_content")
        await self.bind(Keys.Left, "change_focus('{}')".format(Keys.Left))
        await self.bind(Keys.Right, "change_focus('{}')".format(Keys.Right))

    async def action_toggle_consumer_mode(self) -> None:
        if not self.topic_list_widget.has_focus:
            self.focusables.current = self.consumer_mode_widget
            await self.set_focus(self.consumer_mode_widget)
        self.enable_consumer_mode()

    def enable_consumer_mode(self) -> None:
        self.consumer_mode_widget.visible = True
        self.describer_mode_widget.visible = False
        self.consumer_mode_widget.refresh()
        self.describer_mode_widget.refresh()
        self.consumer_mode_widget.consume_topic()
        self.consumer_mode_widget.load_messages()

    async def action_toggle_describer_mode(self) -> None:
        if not self.topic_list_widget.has_focus:
            self.focusables.current = self.describer_mode_widget
            await self.set_focus(self.describer_mode_widget)
        self.enable_describer_mode()

    def enable_describer_mode(self) -> None:
        self.consumer_mode_widget.visible = False
        self.describer_mode_widget.visible = True
        self.describer_mode_widget.reset()
        self.describer_mode_widget.refresh()

    async def action_quit(self) -> None:
        if self.background_lock is not None:
            logger.debug("Shutdown received")
            self.background_lock.set()
        await self.shutdown()

    async def watch_error(self, error: str) -> None:
        show_error = bool(error)
        self.error_widget.message = error
        self.error_widget.visible = show_error

    async def watch_show_help(self, show_help: bool) -> None:
        self.help_widget.visible = show_help

    async def action_toggle_help(self) -> None:
        self.show_help = not self.show_help

    async def action_back(self) -> None:
        self.show_help = False
        self.error = ""

    def handle_exception(self, exception: Exception) -> None:
        message = str(exception)

        if isinstance(exception, KafkaException):
            message = exception.args[0].str()

        self.error = message

        logger.error("Error in runtime: %s", message)
        logger.exception(exception)

    async def action_reload_content(self) -> None:
        self.reload_content()
        self.topic_list_widget.refresh()
        self.topic_header_widget.refresh()
        self.describer_mode_widget.refresh()

    def reload_content(self) -> None:
        selected_topic: Optional[Topic] = None

        if self.topic is not None:
            selected_topic = self.topic

        logger.debug("Reloading content - started")
        try:
            self.topics = self.topic_service.list()
        except Exception as ex:
            self.topics = []
            self.handle_exception(ex)
        logger.debug("Reloading content - finished")

        try:
            if self.topic is not None:
                self.topic = self.topics[self.topics.index(self.topic)]
        except Exception as ex:
            self.error = f"Selected topic [yellow bold]{selected_topic}[/] not found"
            logger.exception(ex)
            self.topic = None

    @property
    def topic(self) -> Optional[Topic]:
        return self.__topic

    @topic.setter
    def topic(self, topic: Optional[Topic]) -> None:
        self.__topic = topic
        self.describer_mode_widget.table = None
        self.describer_mode_widget.refresh()
        self.topic_header_widget.refresh()

    async def action_change_focus(self, key: Keys) -> None:
        focused: Widget = (
            self.focusables.next() if Keys.Right == key else self.focusables.previous()
        )
        if focused.visible:
            await focused.focus()
        else:
            await self.action_change_focus(key)
