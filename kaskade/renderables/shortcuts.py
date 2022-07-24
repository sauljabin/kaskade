from rich.table import Table
from textual.keys import Keys

from kaskade.unicodes import DOWN, DOWN_TRIANGLE, LEFT, RIGHT, UP


class Shortcuts:
    shortcuts = {
        f"navigation {DOWN_TRIANGLE}": {
            "navigate": "{} {} {} {}".format(LEFT, RIGHT, UP, DOWN),
            "help": "?",
            "manual refresh": "f5",
            "close dialog": Keys.Escape,
            "quit": Keys.ControlC,
        },
        f"describer mode {DOWN_TRIANGLE}": {
            "activate mode": Keys.ControlD,
            "next page": "]",
            "previous page": "[",
            "last page": "}",
            "first page": "{",
            "next tab": ">",
            "previous tab": "<",
        },
        f"consumer mode {DOWN_TRIANGLE}": {
            "activate mode": Keys.ControlR,
            "consume next records": "]",
            "consume from beginning": Keys.ControlR,
            "open message": Keys.Enter,
            "close message": Keys.Escape,
        },
    }

    def __str__(self) -> str:
        return str(self.shortcuts)

    def __rich__(self) -> Table:
        table = Table(box=None, expand=False, show_footer=False, show_header=False)
        table.add_column()
        table.add_column(style="yellow bold")
        for category, shortcuts in self.shortcuts.items():
            table.add_row("[blue bold]{}[/]".format(category))
            for action, shortcut in shortcuts.items():
                table.add_row("{}".format(action), "{}".format(shortcut))
            else:
                table.add_row()

        return table
