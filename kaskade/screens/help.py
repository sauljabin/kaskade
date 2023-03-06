from rich.markdown import Markdown
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static

from kaskade.renderables.config_examples import config_example_md
from kaskade.styles.themes import MD_THEME

help_md = f"""
# Navigation

- `TAB` Focus on next element.
- `CTRL+C` Quit.
- `F1` Help window.
- `ESCAPE` Close window.

#  Tables

- `UP` Move the cursor up.
- `DOWN` Move the cursor down.

# Filter

- `LEFT` Move the cursor left.
- `CTRL+LEFT` Move the cursor one word to the left.
- `RIGHT` Move the cursor right.
- `CTRL+RIGHT` Move the cursor one word to the right.
- `BACKSPACE` Delete the character to the left of the cursor.
- `HOME,CTRL+A` Go to the beginning of the input.
- `END,CTRL+E` Go to the end of the input.
- `DELETE,CTRL+D` Delete the character to the right of the cursor.
- `ENTER` Submit the current value of the input.
- `CTRL+W` Delete the word to the left of the cursor.
- `CTRL+U` Delete everything to the left of the cursor.
- `CTRL+F` Delete the word to the right of the cursor.
- `CTRL+K` Delete everything to the right of the cursor.

# Configurations

{config_example_md}
"""


class Help(Screen):
    BINDINGS = [Binding("escape,space,q,question_mark", "pop_screen", "CLOSE")]

    def compose(self) -> ComposeResult:
        yield Static(Markdown(help_md, code_theme=MD_THEME))
