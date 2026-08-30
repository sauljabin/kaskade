import re
import shlex
import subprocess
import sys

from rich.console import Console

SVG_VIEWBOX = re.compile(r'(<svg\b)(?![^>]*\bwidth=)(?=[^>]*\bviewBox="0 0 ([\d.]+) ([\d.]+)")')


def normalize_svg(svg: str) -> str:
    """Add intrinsic dimensions and remove trailing whitespace from an SVG."""
    svg = SVG_VIEWBOX.sub(
        lambda match: (f'{match.group(1)} width="{match.group(2)}" height="{match.group(3)}"'),
        svg,
        count=1,
    )
    return "\n".join(line.rstrip() for line in svg.splitlines()) + "\n"


class CommandProcessor:
    def __init__(self, commands: dict[str, str], rollback: dict[str, str] | None = None) -> None:
        if rollback is None:
            rollback = {}
        self.commands = commands
        self.rollback = rollback
        self.console = Console()

    def run(self) -> str:
        output = ""
        for name, command in self.commands.items():
            result = self.execute_command(name, command)
            if result.returncode:
                self.console.print(
                    "\n[bold red]Error[/] when executing "
                    f'[bold blue]"{name}" ([bold yellow]{command}[/])[/]:exclamation::\n'
                    f"[red]{result.stdout}{result.stderr}[/]\n"
                )

                if self.rollback:
                    self.console.print("[bold yellow]Rolling back:[/]")
                    for rollback_name, rollback_command in self.rollback.items():
                        self.execute_command(rollback_name, rollback_command)

                sys.exit(result.returncode)
            else:
                output += result.stdout

        return output

    def execute_command(self, name: str, command: str) -> subprocess.CompletedProcess:
        self.console.print()
        self.console.print(f"[bold blue]{name.lower()}:")
        self.console.print(f"[bold yellow]{command}[/]")
        return subprocess.run(shlex.split(command), capture_output=True, text=True, check=False)
