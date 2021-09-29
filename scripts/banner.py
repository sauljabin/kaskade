from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel

from kaskade.kaskade import kaskade

console = Console(record=True)

panel = Panel.fit(kaskade.riched_name(), box=box.DOUBLE, border_style="magenta")

console.print(Columns([panel]))

CONSOLE_HTML_FORMAT = """\
<pre style="font-family:Menlo,'DejaVu Sans Mono',consolas,'Courier New',monospace">
{code}
</pre>
"""


def main():
    console.save_html("BANNER.md", inline_styles=True, code_format=CONSOLE_HTML_FORMAT)


if __name__ == "__main__":
    main()
