from rich.table import Table
from textual.keys import Keys

from kaskade.unicodes import DOWN, LEFT, RIGHT, UP


class Shortcuts:
    shortcuts = {
        "navigation:": {
            "navigate": "{} {} {} {}".format(LEFT, RIGHT, UP, DOWN),
            "help": "?",
            "manual refresh": "f5",
            "close dialog": Keys.Escape,
            "quit": Keys.ControlC,
        },
        "describer mode:": {
            "activate mode": Keys.ControlD,
            "next page": "]",
            "previous page": "[",
            "last page": "}",
            "first page": "{",
            "next tab": ">",
            "previous tab": "<",
        },
        "consumer mode:": {
            "activate mode": Keys.ControlR,
            "consume next records": "]",
            "consume from beginning": Keys.ControlR,
        },
    }

    def __str__(self) -> str:
        return str(self.shortcuts)

    def __rich__(self) -> Table:
        table = Table(box=None, expand=False, show_footer=False, show_header=False)
        table.add_column(style="magenta bold")
        table.add_column(style="yellow bold")
        for category, shortcuts in self.shortcuts.items():
            table.add_row("[blue bold]{}[/]".format(category))
            for action, shortcut in shortcuts.items():
                table.add_row("{}".format(action), "{}".format(shortcut))
            else:
                table.add_row()

        return table
