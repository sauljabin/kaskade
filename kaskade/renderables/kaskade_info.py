from rich.table import Table

from kaskade import APP_DOC, APP_HOME, APP_LICENSE, APP_LOG


class KaskadeInfo:
    def __rich__(self) -> Table:
        info = Table(
            box=None,
            expand=False,
            show_header=False,
            show_edge=False,
            padding=(0, 1, 0, 0),
        )
        info.add_column(style="bright_magenta bold")
        info.add_column(style="yellow bold")
        info.add_row("home path:", APP_HOME)
        info.add_row("logs path:", APP_LOG)
        info.add_row("license:", APP_LICENSE)
        info.add_row("docs:", APP_DOC)
        return info
