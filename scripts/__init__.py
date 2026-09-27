import re
import shlex
import subprocess
import sys
from xml.etree import ElementTree

from rich.cells import cell_len
from rich.console import Console

SVG_VIEWBOX = re.compile(r'(<svg\b)(?![^>]*\bwidth=)(?=[^>]*\bviewBox="0 0 ([\d.]+) ([\d.]+)")')
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
SVG = f"{{{SVG_NAMESPACE}}}"
# Rich's SVG export metrics: 20px glyphs 12.2px wide, 24.4px lines offset by 1.5px.
SVG_BASELINE = 20
SVG_CELL_WIDTH = 12.2
SVG_LINE_HEIGHT = 24.4
SVG_LINE_OFFSET = 1.5
SVG_CLASS_FILL = re.compile(r"\.([\w-]+) \{ fill: (#[0-9a-fA-F]{6})")
BOX_STROKE = 1.5
BOX_DOUBLE_OFFSET = 3
# Horizontal arm (-1 left, 1 right), vertical arm (-1 up, 1 down), double line.
# A straight line has no arm on the other axis.
BOX_GLYPHS = {
    "─": (1, 0, False),
    "│": (0, 1, False),
    "┌": (1, 1, False),
    "┐": (-1, 1, False),
    "└": (1, -1, False),
    "┘": (-1, -1, False),
    "═": (1, 0, True),
    "║": (0, 1, True),
    "╔": (1, 1, True),
    "╗": (-1, 1, True),
    "╚": (1, -1, True),
    "╝": (-1, -1, True),
}


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


def draw_box_glyphs(svg: str) -> str:
    """Draw a Rich SVG's box-drawing glyphs as paths between its text runs.

    Linux and Android borrow these glyphs from fallback fonts whose widths and
    heights differ from the monospace cells. Borders then split apart, and the
    wider glyphs squeeze the rest of their text element into its textLength.
    """
    root = ElementTree.fromstring(svg)
    matrix = next(
        group for group in root.iter(f"{SVG}g") if group.get("class", "").endswith("-matrix")
    )
    style = root.find(f"{SVG}style")
    fills = dict(SVG_CLASS_FILL.findall(style.text or "")) if style is not None else {}
    commands: dict[str, list[str]] = {}
    children = []
    for child in matrix:
        color = fills.get(child.get("class", ""))
        if child.tag == f"{SVG}text" and color and child.text:
            children.extend(_split_box_glyphs(child, commands.setdefault(color, [])))
        else:
            children.append(child)

    paths = [_box_glyph_path(color, path) for color, path in commands.items() if path]
    matrix[:] = paths + children
    ElementTree.register_namespace("", SVG_NAMESPACE)
    # Keep Rich's escaped no-break spaces.
    return ElementTree.tostring(root, encoding="unicode").replace("\xa0", "&#160;")


def _split_box_glyphs(text: ElementTree.Element, commands: list[str]) -> list[ElementTree.Element]:
    left = float(text.get("x", 0))
    top = float(text.get("y", 0)) - SVG_BASELINE + SVG_LINE_OFFSET
    runs: list[tuple[float, str]] = []
    run_left, run = left, ""
    for character in text.text or "":
        glyph = BOX_GLYPHS.get(character)
        if glyph is None:
            run_left = run_left if run else left
            run += character
        else:
            commands.extend(_box_path(glyph, left, top))
            runs.extend([(run_left, run)] if run else [])
            run = ""
        left += cell_len(character) * SVG_CELL_WIDTH
    runs.extend([(run_left, run)] if run else [])
    if runs == [(float(text.get("x", 0)), text.text)]:
        return [text]
    # Rich draws backgrounds as rectangles, so blank runs carry nothing.
    return [_text_run(text, run_left, run) for run_left, run in runs if run.strip()]


def _text_run(text: ElementTree.Element, left: float, run: str) -> ElementTree.Element:
    element = ElementTree.Element(text.tag, dict(text.attrib))
    element.set("x", _n(left))
    element.set("textLength", _n(cell_len(run) * SVG_CELL_WIDTH))
    element.text = run
    element.tail = text.tail
    return element


def _box_glyph_path(color: str, commands: list[str]) -> ElementTree.Element:
    path = ElementTree.Element(
        f"{SVG}path",
        {
            "fill": "none",
            "stroke": color,
            "stroke-width": f"{BOX_STROKE:g}",
            "stroke-linecap": "square",
            "d": "".join(commands),
        },
    )
    path.tail = "\n"
    return path


def _box_path(glyph: tuple[int, int, bool], left: float, top: float) -> list[str]:
    horizontal, vertical, double = glyph
    center_x = left + SVG_CELL_WIDTH / 2
    center_y = top + SVG_LINE_HEIGHT / 2
    offsets = (-BOX_DOUBLE_OFFSET, BOX_DOUBLE_OFFSET) if double else (0,)
    if vertical == 0:
        return [f"M{_n(left)} {_n(center_y + o)}H{_n(left + SVG_CELL_WIDTH)}" for o in offsets]
    if horizontal == 0:
        return [f"M{_n(center_x + o)} {_n(top)}V{_n(top + SVG_LINE_HEIGHT)}" for o in offsets]
    edge_x = center_x + horizontal * SVG_CELL_WIDTH / 2
    edge_y = center_y + vertical * SVG_LINE_HEIGHT / 2
    return [
        f"M{_n(edge_x)} {_n(center_y + vertical * o)}H{_n(center_x + horizontal * o)}V{_n(edge_y)}"
        for o in offsets
    ]


def _n(value: float) -> str:
    return f"{round(value, 2):g}"


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
