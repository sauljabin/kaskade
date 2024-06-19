from rich.columns import Columns
from rich.console import RenderableType
from textual.widgets import Static

from kaskade.kafka.models import Cluster
from kaskade.renderables.cluster_info import ClusterInfo
from kaskade.renderables.kaskade_name import KaskadeName


class Header(Static):
    cluster = Cluster()

    def render(self) -> RenderableType:
        kaskade_name = KaskadeName(include_version=True)
        cluster_info = ClusterInfo(self.cluster)
        return Columns([kaskade_name, cluster_info], padding=3)
