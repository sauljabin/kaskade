from rich.table import Table

from kaskade.unicodes import DOWN, LEFT, RIGHT, UP


class Shortcuts:
    shortcuts = {
        "navigate": "{} {} {} {}".format(LEFT, RIGHT, UP, DOWN),
        "help": "?",
        "quit": "q",
        "back": "esc",
        "manual refresh": "f5",
        "next page": "]",
        "previous page": "[",
        "last page": "}",
        "first page": "{",
        "next tab": ">",
        "previous tab": "<",
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
