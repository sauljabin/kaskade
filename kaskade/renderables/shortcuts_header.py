from itertools import zip_longest

from rich.table import Table

from kaskade.unicodes import DOWN, LEFT, RIGHT, UP


class ShortcutsHeader:
    shortcuts = {
        "navigate": "{} {} {} {}".format(LEFT, RIGHT, UP, DOWN),
        "help": "?",
        "quit": "q",
        "back": "esc",
    }

    def __str__(self) -> str:
        return str(self.shortcuts)

    def __rich__(self) -> Table:
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
