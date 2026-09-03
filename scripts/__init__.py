import re
import shlex
import subprocess
import sys
from xml.etree import ElementTree

from rich.console import Console

SVG_VIEWBOX = re.compile(r'(<svg\b)(?![^>]*\bwidth=)(?=[^>]*\bviewBox="0 0 ([\d.]+) ([\d.]+)")')
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
SVG = f"{{{SVG_NAMESPACE}}}"


def normalize_svg(svg: str) -> str:
    """Add intrinsic dimensions and remove trailing whitespace from an SVG."""
    svg = SVG_VIEWBOX.sub(
        lambda match: (f'{match.group(1)} width="{match.group(2)}" height="{match.group(3)}"'),
        svg,
        count=1,
    )
    return "\n".join(line.rstrip() for line in svg.splitlines()) + "\n"


def remove_svg_terminal_chrome(svg: str) -> str:
    """Remove Rich's window frame while retaining the rendered terminal content."""
    root = ElementTree.fromstring(svg)
    terminal_group = next(
        (
            child
            for child in root
            if child.tag == f"{SVG}g" and "clip-terminal" in child.get("clip-path", "")
        ),
        None,
    )
    terminal_clip = next(
        (element for element in root.iter() if element.get("id", "").endswith("-clip-terminal")),
        None,
    )
    if terminal_group is None or terminal_clip is None:
        raise ValueError("Rich terminal content was not found in the exported SVG")

    clip_rect = terminal_clip.find(f"{SVG}rect")
    if clip_rect is None:
        raise ValueError("Rich terminal clip dimensions were not found in the exported SVG")

    for child in list(root):
        if child.tag not in {f"{SVG}style", f"{SVG}defs"} and child is not terminal_group:
            root.remove(child)

    terminal_group.attrib.pop("transform", None)
    root.attrib.pop("width", None)
    root.attrib.pop("height", None)
    root.set("viewBox", f'0 0 {clip_rect.get("width")} {clip_rect.get("height")}')
    ElementTree.register_namespace("", SVG_NAMESPACE)
    ElementTree.indent(root, space="    ")
    return ElementTree.tostring(root, encoding="unicode")


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
