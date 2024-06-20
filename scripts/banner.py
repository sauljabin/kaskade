from rich import box
from rich.console import Console
from rich.panel import Panel

from kaskade.renderables import KaskadeName


def main():
    console = Console()
    panel = Panel.fit(KaskadeName(include_slogan=True), box=box.DOUBLE, border_style="magenta")
    console.print(panel)


if __name__ == "__main__":
    main()
