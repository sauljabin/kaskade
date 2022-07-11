from rich.columns import Columns

from kaskade.renderables.cluster_info import ClusterInfo
from kaskade.renderables.kaskade_name import KaskadeName
from kaskade.renderables.shortcuts_header import ShortcutsHeader
from kaskade.widgets.tui_widget import TuiWidget


class Header(TuiWidget):
    def on_mount(self) -> None:
        self.layout_size = 6

    def render(self) -> Columns:
        cluster_info = ClusterInfo(self.tui.cluster)
        kaskade_name = KaskadeName()
        shortcuts = ShortcutsHeader()
        return Columns([kaskade_name, cluster_info, shortcuts], padding=3)
