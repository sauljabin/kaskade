from rich import box
from rich.console import Console
from rich.panel import Panel

from kaskade.kaskade import KASKADE


def main():
    console = Console(record=True)
    panel = Panel.fit(KASKADE.riched_name(), box=box.DOUBLE, border_style="magenta")
    console.print(panel)


if __name__ == "__main__":
    main()
