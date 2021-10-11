import sys
from typing import Optional

from rich.console import Console

from kaskade.config import Config
from kaskade.renderables.kaskade_name import KaskadeName
from kaskade.renderables.kaskade_version import KaskadeVersion
from kaskade.tui import Tui


class Cli:
    def __init__(
        self, print_version: Optional[bool], config_file: Optional[str]
    ) -> None:
        self.print_version = print_version
        self.config_file = config_file

    def run(self) -> None:
        try:
            self.option_version()
            self.run_tui()
        except Exception as ex:
            console = Console()
            console.print(
                ":thinking_face: [bold red]A problem has occurred[/]: {}".format(
                    str(ex)
                )
            )

    def run_tui(self) -> None:
        Tui.run(config=Config(self.config_file))

    def option_version(self) -> None:
        if self.print_version:
            console = Console()
            console.print(KaskadeName())
            console.print(KaskadeVersion())
            sys.exit(0)
