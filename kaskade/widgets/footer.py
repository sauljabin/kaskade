from rich.align import Align
from rich.columns import Columns
from rich.padding import Padding
from textual.reactive import Reactive
from textual.widget import Widget

from kaskade.renderables.kaskade_version import KaskadeVersion


class Footer(Widget):
    mode = Reactive("describer")

    def on_mount(self) -> None:
        self.layout_size = 1

    def render(self) -> Columns:
        mode_text = Align.right(
            Padding(
                "[bold]{}[/] mode".format(self.mode),
                pad=(0, 1, 0, 1),
                style="black on yellow",
                expand=False,
            )
        )
        return Columns([KaskadeVersion(), mode_text], expand=True)
