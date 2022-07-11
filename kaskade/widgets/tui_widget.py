from typing import TYPE_CHECKING, cast

from textual.widget import Widget

if TYPE_CHECKING:
    from kaskade.tui import Tui


class TuiWidget(Widget):
    @property
    def tui(self) -> "Tui":
        return cast("Tui", self.app)
