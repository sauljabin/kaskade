from rich.console import RenderableType
from textual.widget import Widget

from kaskade.renderables.kaskade_version import KaskadeVersion


class Footer(Widget):
    def on_mount(self) -> None:
        self.layout_size = 1

    def render(self) -> RenderableType:
        return KaskadeVersion()
