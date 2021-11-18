import time
from threading import Thread
from typing import List, Optional, Union, cast

from rich.align import Align
from rich.columns import Columns
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade import logger, styles
from kaskade.kafka.consumer_service import ConsumerService
from kaskade.kafka.models import Record
from kaskade.renderables.topic_info import TopicInfo


class ConsumerMode(Widget):
    has_focus = Reactive(False)
    is_loading = Reactive(True)
    spinner = Spinner("dots")
    loading_text = Text("loading")
    consumer_service: Optional[ConsumerService] = None
    records: Optional[List[Record]] = None

    def consume_topic(self) -> None:
        if self.app.topic is None:
            return
        try:
            logger.debug("Consuming another topic")
            self.consumer_service = ConsumerService(self.app.config, self.app.topic)
        except Exception as ex:
            self.app.handle_exception(ex)

    def page_size(self) -> int:
        return cast(int, self.size.height)

    def background_execution(self) -> None:
        self.is_loading = True
        self.records = None
        try:
            while self.page_size() == 0:
                time.sleep(0.5)
            logger.debug(
                "Start consuming in background: %s, total to consume: %s",
                self.consumer_service,
                self.page_size(),
            )
            if self.consumer_service is not None:
                self.records = self.consumer_service.consume(self.page_size())
            logger.debug("End consuming in background")
        except Exception as ex:
            self.app.handle_exception(ex)
        self.is_loading = False
        self.refresh()

    def load_messages(self) -> None:
        if self.app.topic is None:
            return

        background_thread = Thread(target=self.background_execution, args=())
        background_thread.start()

    def loading(self) -> None:
        if self.is_loading:
            self.refresh()

    def on_mount(self) -> None:
        self.set_interval(0.1, self.loading)

    def on_focus(self) -> None:
        self.has_focus = True

    def on_blur(self) -> None:
        self.has_focus = False

    def render(self) -> Panel:
        to_render: Union[Align, TopicInfo, str] = Align.center(
            "Not selected", vertical="middle"
        )

        if self.app.topic is not None:
            if self.is_loading:
                self.spinner.style = ""
                self.loading_text.style = ""

                if self.has_focus:
                    self.spinner.style = "magenta"
                    self.loading_text.style = "magenta"
                to_render = Align.center(
                    Columns([self.spinner, self.loading_text]), vertical="middle"
                )
            elif self.records is not None:
                to_render = str(self.records)

        return Panel(
            to_render,
            title="consumer",
            border_style=styles.BORDER_FOCUSED if self.has_focus else styles.BORDER,
            box=styles.BOX,
            title_align="left",
            padding=0,
        )
