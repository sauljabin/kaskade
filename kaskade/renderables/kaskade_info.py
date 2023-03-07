from rich.table import Table

from kaskade import APP_DOC, APP_HOME, APP_LICENSE, APP_LOG
from kaskade.styles.colors import PRIMARY, SECONDARY


class KaskadeInfo:
    def __rich__(self) -> Table:
        info = Table(
            box=None,
            expand=False,
            show_header=False,
            show_edge=False,
            padding=(0, 1, 0, 0),
        )
        info.add_column(style=f"{PRIMARY} bold")
        info.add_column(style=f"{SECONDARY} bold")
        info.add_row("HOME:", APP_HOME)
        info.add_row("LOGS:", APP_LOG)
        info.add_row("LICENSE:", APP_LICENSE)
        info.add_row("DOC:", APP_DOC)
        return info
