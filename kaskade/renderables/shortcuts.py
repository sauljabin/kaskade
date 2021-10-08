from itertools import zip_longest

from rich.table import Table
from textual.keys import Keys

from kaskade.unicodes import DOWN, LEFT, RIGHT, UP


class Shortcuts:
    shortcuts = {
        "quit": "q",
        "refresh": Keys.F5.value,
        "navigate": "{} {} {} {}".format(LEFT, RIGHT, UP, DOWN),
        "next page": Keys.PageDown.value,
        "previous page": Keys.PageUp.value,
        "last page": Keys.ControlPageDown.value,
        "first page": Keys.ControlPageUp.value,
    }

    def __str__(self):
        return str(self.shortcuts)

    def __rich__(self):
        max_len = 4
        items = [
            ("{}:".format(key), value) for key, value in list(self.shortcuts.items())
        ]

        table = Table(box=None, expand=False)
        shortcuts_chunks = []

        for i in range(0, len(items), max_len):
            table.add_column(style="magenta bold")
            table.add_column(style="yellow bold")
            chunk = items[i : i + max_len]
            shortcuts_chunks.append(chunk)

        rows = zip_longest(*shortcuts_chunks, fillvalue=())

        for row in rows:
            cells = [cell for pair in row for cell in pair]
            table.add_row(*cells)

        return table


if __name__ == "__main__":
    from rich.console import Console

    console = Console()
    shortcuts = Shortcuts()
    print(shortcuts)
    console.print(shortcuts)
