from rich.console import Group
from rich.text import Text
from textual.widget import Widget

from kaskade import APP_BANNER, APP_VERSION
from kaskade.colors import PRIMARY, SECONDARY


class KaskadeBanner(Widget):
    def __init__(self, *, include_version: bool = False, include_slogan: bool = False):
        super().__init__()
        self.include_slogan = include_slogan
        self.include_version = include_version

    def render(self) -> Group:
        kaskade_name = Text(
            APP_BANNER,
            style=f"{PRIMARY} bold",
        )
        version_text = Text("", justify="right")

        if self.include_slogan:
            version_text.append("a text user interface for kafka ", style=f"{SECONDARY}")

        if self.include_version:
            version_text.append(f"v{APP_VERSION}", style=f"{SECONDARY}")

        return Group(kaskade_name, version_text)
