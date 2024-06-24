from rich.table import Table
from textual.app import App, ComposeResult, RenderResult
from textual.containers import Container
from textual.keys import Keys
from textual.widget import Widget
from textual.widgets import DataTable

from kaskade.colors import PRIMARY
from kaskade.unicodes import LEFT, RIGHT, UP, DOWN
from kaskade.widgets import KaskadeBanner


class Shortcuts(Widget):

    def render(self) -> RenderResult:
        table = Table(box=None, show_header=False, padding=(0, 1, 0, 0))
        table.add_column(style=f"bold {PRIMARY}")
        table.add_column()

        table.add_row("show", "enter")
        table.add_row("scroll", f"{LEFT} {RIGHT} {UP} {DOWN}")
        table.add_row("next", ">")
        table.add_row("quit", Keys.ControlC)

        return table


class Header(Widget):

    def compose(self) -> ComposeResult:
        yield KaskadeBanner(short=False, include_version=True, include_slogan=True)
        yield Shortcuts()


class Body(Container):
    def compose(self) -> ComposeResult:
        yield DataTable()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.fixed_columns = 1
        table.border_title = "loading..."
        table.border_subtitle = f"\\[[{PRIMARY}]consumer mode[/]]"


class KaskadeConsumer(App):
    CSS_PATH = "styles.css"

    def __init__(self, topic: str, kafka_conf: dict[str, str], schema_conf: dict[str, str]):
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Body()
