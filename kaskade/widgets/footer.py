from textual.widget import Widget

from kaskade.renderables.kaskade_version import KaskadeVersion


class Footer(Widget):
    def on_mount(self):
        self.layout_size = 1

    def render(self):
        return KaskadeVersion()
