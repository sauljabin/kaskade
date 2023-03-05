from rich.markdown import Markdown
from textual.app import ComposeResult
from textual.binding import Binding
from textual.keys import Keys
from textual.screen import Screen
from textual.widgets import Static

from kaskade.styles.unicodes import DOWN, UP

help_md = f"""
# Help
## Navigation
- **Navigate**: {UP} {DOWN}
- **Focus on next**: {Keys.Tab}
- **Quit**: {Keys.ControlC}
- **Help window**: ?
- **Close dialog**: {Keys.Escape}
"""


class Help(Screen):
    BINDINGS = [Binding("escape,space,q,question_mark", "pop_screen", "CLOSE")]

    def compose(self) -> ComposeResult:
        yield Static(Markdown(help_md))
