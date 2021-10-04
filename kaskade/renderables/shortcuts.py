from rich.table import Table
from textual.keys import Keys

from kaskade.unicodes import DOWN, LEFT, RIGHT, UP


class Shortcuts:
    shortcuts = {
        "quit": "q",
        "refresh": Keys.F5.value,
        "navigate": "{} {} {} {}".format(LEFT, RIGHT, UP, DOWN),
    }

    def __str__(self):
        return str(self.shortcuts)

    def __rich__(self):
        shortcuts = Table(box=None, expand=False)
        shortcuts.add_column(style="magenta bold")
        shortcuts.add_column(style="yellow bold")

        for action, shortcut in self.shortcuts.items():
            shortcuts.add_row("{}:".format(action), shortcut)

        return shortcuts


if __name__ == "__main__":
    from rich.console import Console

    console = Console()
    console.print(Shortcuts())
