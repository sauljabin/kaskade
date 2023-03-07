from typing import Type

from textual.app import App, CSSPathType
from textual.binding import Binding
from textual.driver import Driver
from textual.keys import Keys

from kaskade.config import Config
from kaskade.kafka.cluster_service import ClusterService
from kaskade.screens.help import Help
from kaskade.screens.topic_list import TopicList
from kaskade.styles.colors import DESIGN


class Tui(App[None]):
    CSS_PATH = "tui.css"
    SCREENS = {"help": Help}
    BINDINGS = [
        Binding(Keys.ControlC, "quit", "QUIT"),
        Binding(Keys.F1, "push_screen('help')", "HELP"),
    ]

    def __init__(
        self,
        config: Config,
        driver_class: Type[Driver] | None = None,
        css_path: CSSPathType | None = None,
        watch_css: bool = False,
    ):
        super().__init__(driver_class, css_path, watch_css)
        self.config = config
        self.cluster_service = ClusterService(self.config)
        self.cluster = self.cluster_service.current()

    def on_mount(self) -> None:
        topic_list_widget = TopicList()
        topic_list_widget.cluster = self.cluster
        self.push_screen(topic_list_widget)

        self.design = DESIGN
        self.refresh_css()
