import time
from threading import Thread
from typing import List, Optional, Union, cast

from rich.align import Align
from rich.columns import Columns
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text
from textual import events
from textual.keys import Keys
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade import logger, styles
from kaskade.kafka.consumer_service import ConsumerService
from kaskade.kafka.models import Record
from kaskade.renderables.records_table import RecordsTable

TABLE_BOTTOM_PADDING = 4
CLICK_OFFSET = 1


class ConsumerMode(Widget):
    has_focus = Reactive(False)
    is_loading = Reactive(False)
    spinner = Spinner("dots")
    loading_text = Text("loading")
    consumer_service: Optional[ConsumerService] = None
    records: List[Record] = []
    total_reads = 0
    __row = 0

    def consume_topic(self) -> None:
        if self.app.topic is None:
            return

        if self.is_loading:
            return

        try:
            logger.debug("Consuming another topic")
            self.total_reads = 0
            self.__row = 0
            if self.consumer_service is not None:
                self.consumer_service.close()
            self.consumer_service = ConsumerService(self.app.config, self.app.topic)
        except Exception as ex:
            self.app.handle_exception(ex)

    def page_size(self) -> int:
        if self.size.height < TABLE_BOTTOM_PADDING:
            return 0
        return cast(int, self.size.height - TABLE_BOTTOM_PADDING)

    def background_execution(self) -> None:
        if self.is_loading:
            return

        self.is_loading = True
        self.records = []
        try:
            while self.page_size() <= 0:
                time.sleep(0.5)
            logger.debug(
                "Start consuming in background: %s, total to consume: %s",
                self.consumer_service,
                self.page_size(),
            )
            if self.consumer_service is not None:
                self.records = self.consumer_service.consume(self.page_size())
                self.total_reads += len(self.records)
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
        to_render: Union[Align, RecordsTable, str] = Align.center(
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
                to_render = RecordsTable(
                    self.records, self.total_reads, self.page_size(), row=self.row
                )

        title = "records ([blue]group[/] [yellow]{}[/])".format(
            self.consumer_service.id if self.consumer_service is not None else "unknown"
        )
        return Panel(
            to_render,
            title=title,
            border_style=styles.BORDER_FOCUSED if self.has_focus else styles.BORDER,
            box=styles.BOX,
            title_align="left",
            padding=0,
        )

    def on_click(self, event: events.Click) -> None:
        self.row = event.y - CLICK_OFFSET
        self.refresh()

    def on_key(self, event: events.Key) -> None:
        if self.is_loading:
            return

        key = event.key
        if key == ">":
            self.load_messages()
            self.row = 0
        elif key == Keys.Up:
            self.row -= 1
        elif key == Keys.Down:
            self.row += 1

        self.refresh()

    @property
    def row(self) -> int:
        return self.__row

    @row.setter
    def row(self, row: int) -> None:
        if row <= 0:
            self.__row = len(self.records)
        elif row > len(self.records):
            self.__row = 1
        else:
            self.__row = row
