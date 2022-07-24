import time
from threading import Thread
from typing import List, Optional, Union

from rich.align import Align
from rich.columns import Columns
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text
from textual import events
from textual.keys import Keys
from textual.reactive import Reactive

from kaskade import logger, styles
from kaskade.kafka.consumer_service import ConsumerService
from kaskade.kafka.models import Record
from kaskade.renderables.kafka_record import KafkaRecord
from kaskade.renderables.records_table import RecordsTable
from kaskade.widgets.tui_widget import TuiWidget

TABLE_BOTTOM_PADDING = 4
CLICK_OFFSET = 1


class ConsumerMode(TuiWidget):
    has_focus = Reactive(False)
    is_loading = Reactive(False)
    spinner = Spinner("dots")
    loading_text = Text("loading")
    consumer_service: Optional[ConsumerService] = None
    records: List[Record] = []
    record: Optional[Record] = None
    total_reads = 0
    __table_row = 0
    __record_line = 1
    total_record_lines = 0

    def consume_topic(self) -> None:
        if self.tui.topic is None:
            return

        if self.is_loading:
            return

        try:
            logger.debug("Consuming another topic")
            self.total_reads = 0
            self.__table_row = 0
            if self.consumer_service is not None:
                self.consumer_service.close()
            self.consumer_service = ConsumerService(self.tui.config, self.tui.topic)
        except Exception as ex:
            self.tui.handle_exception(ex)

    def page_size(self) -> int:
        if self.size.height < TABLE_BOTTOM_PADDING:
            return 0
        return self.size.height - TABLE_BOTTOM_PADDING

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
            self.tui.handle_exception(ex)
        self.is_loading = False
        self.refresh()

    def load_messages(self) -> None:
        if self.tui.topic is None:
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
        to_render: Union[Align, RecordsTable, str, KafkaRecord] = Align.center(
            "Not selected", vertical="middle"
        )

        if self.tui.topic is not None:
            if self.is_loading:
                self.spinner.style = ""
                self.loading_text.style = ""

                if self.has_focus:
                    self.spinner.style = "magenta"
                    self.loading_text.style = "magenta"
                to_render = Align.center(
                    Columns([self.spinner, self.loading_text]), vertical="middle"
                )
            elif self.record is not None:
                logger.debug("imprimiendo la linea %s", self.record_line)
                to_render = KafkaRecord(
                    self.record, self.page_size() + 2, line=self.record_line
                )
            elif self.records is not None:
                to_render = RecordsTable(
                    self.records, self.total_reads, self.page_size(), row=self.table_row
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

    async def on_click(self, event: events.Click) -> None:
        self.table_row = event.y - CLICK_OFFSET
        self.refresh()

    def on_key(self, event: events.Key) -> None:
        if self.is_loading:
            return

        key = event.key
        if key == "]":
            self.record = None
            self.load_messages()
            self.table_row = 0
        elif key == Keys.Up:
            if self.record is not None:
                self.record_line -= 1
            else:
                self.table_row -= 1
        elif key == Keys.Down:
            if self.record is not None:
                self.record_line += 1
            else:
                self.table_row += 1
        elif key == Keys.Enter:
            self.record = self.records[self.table_row - 1]
            self.total_record_lines = self.record.json().count("\n") + 1
            self.record_line = 1
        elif key == Keys.Escape:
            self.record = None

        self.refresh()

    @property
    def table_row(self) -> int:
        return self.__table_row

    @table_row.setter
    def table_row(self, row: int) -> None:
        if row <= 0:
            self.__table_row = len(self.records)
        elif row > len(self.records):
            self.__table_row = 1
        else:
            self.__table_row = row

    @property
    def record_line(self) -> int:
        return self.__record_line

    @record_line.setter
    def record_line(self, line: int) -> None:
        if line <= 0:
            self.__record_line = 1
        elif line + self.page_size() + 1 > self.total_record_lines:
            pass
        else:
            self.__record_line = line

    async def on_resize(self, event: events.Resize) -> None:
        self.__record_line = 1
        self.refresh()
