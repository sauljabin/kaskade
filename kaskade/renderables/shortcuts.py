from rich.table import Table

from kaskade.unicodes import DOWN, LEFT, RIGHT, UP


class Shortcuts:
    shortcuts = {
        "help": "?",
        "quit": "q",
        "navigate": "{} {} {} {}".format(LEFT, RIGHT, UP, DOWN),
        "default view": "esc",
        "refresh": "f5",
        "next page": "page down",
        "previous page": "page up",
        "last page": "l",
        "first page": "f",
        "next tab": "]",
        "previous tab": "[",
    }

    def __str__(self) -> str:
        return str(self.shortcuts)

    def __rich__(self) -> Table:
        table = Table(box=None, expand=False, show_footer=False, show_header=False)
        table.add_column(style="magenta bold")
        table.add_column(style="yellow bold")
        for action, shortcut in self.shortcuts.items():
            table.add_row("{}:".format(action), "{}".format(shortcut))

        return table
