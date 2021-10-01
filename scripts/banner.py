from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel

from kaskade.kaskade import KASKADE

console = Console(record=True)

panel = Panel.fit(KASKADE.riched_name(), box=box.DOUBLE, border_style="magenta")


def main():
    console.print(Columns([panel]))


if __name__ == "__main__":
    main()
