from rich.columns import Columns
from textual.widget import Widget

from kaskade.renderables.cluster_info import ClusterInfo
from kaskade.renderables.kaskade_name import KaskadeName
from kaskade.renderables.shortcuts_header import ShortcutsHeader


class Header(Widget):
    def on_mount(self) -> None:
        self.layout_size = 6

    def render(self) -> Columns:
        cluster_info = ClusterInfo(self.app.cluster)
        kaskade_name = KaskadeName()
        shortcuts = ShortcutsHeader()
        return Columns([kaskade_name, cluster_info, shortcuts], padding=3)
