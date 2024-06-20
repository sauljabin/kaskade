from textual.app import ComposeResult
from textual.widgets import Static

from kaskade.renderables import KaskadeName, KaskadeInfo


class Header(Static):
    def compose(self) -> ComposeResult:
        yield Static(KaskadeInfo())
        yield Static(KaskadeName(include_version=True), id="name")
