import asyncio
import os
import re
from pathlib import Path
from xml.etree import ElementTree

from textual.app import ComposeResult

from kaskade.banner import KaskadeBanner
from kaskade.themes import KaskadeApp
from scripts import SVG, SVG_NAMESPACE, normalize_svg, remove_svg_terminal_chrome

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGES_DIRECTORY = PROJECT_ROOT / "images"
BANNER_PATH = IMAGES_DIRECTORY / "banner.svg"
BORDERLESS_BANNER_PATH = IMAGES_DIRECTORY / "banner-borderless.svg"
BANNER_SIZE = (42, 8)
# Rich's SVG export metrics: 20px glyphs, 24.4px lines offset by 1.5px.
SVG_BASELINE = 20
SVG_LINE_HEIGHT = 24.4
SVG_LINE_OFFSET = 1.5
FRAME_GLYPHS = frozenset("╔═╗║╚╝")
FRAME_LINE_GAP = 6
FRAME_STROKE = 1.5


class Banner(KaskadeApp):
    CSS_PATH = str(PROJECT_ROOT / "kaskade" / "styles.css")
    DEFAULT_CSS = """
    KaskadeBanner {
        width: 40;
        height: 8;
        border: double $primary;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield KaskadeBanner(include_slogan=True)


class BorderlessBanner(Banner):
    CSS = """
    Screen.main-view-screen {
        background: $background;
    }

    KaskadeBanner {
        background: $background;
    }
    """


async def _render(app: Banner) -> str:
    async with app.run_test(size=BANNER_SIZE) as pilot:
        await pilot.pause()
        return app.export_screenshot(title="Kaskade", simplify=True)


async def generate_banner() -> tuple[Path, Path]:
    """Render framed README and borderless site banners as SVG files."""
    framed_svg = _draw_frame(await _render(_new_banner(Banner)))
    borderless_svg = _draw_frame(await _render(_new_banner(BorderlessBanner)))

    IMAGES_DIRECTORY.mkdir(parents=True, exist_ok=True)
    BANNER_PATH.write_text(normalize_svg(framed_svg), encoding="utf-8")
    BORDERLESS_BANNER_PATH.write_text(
        normalize_svg(remove_svg_terminal_chrome(borderless_svg)), encoding="utf-8"
    )
    return BANNER_PATH, BORDERLESS_BANNER_PATH


def _draw_frame(svg: str) -> str:
    """Replace the double border glyphs with two rectangles through their cells.

    Linux and Android borrow box-drawing glyphs from fallback fonts whose widths
    and heights differ from the monospace cells, which breaks the frame apart.
    """
    root = ElementTree.fromstring(svg)
    matrix = next(
        element for element in root.iter(f"{SVG}g") if element.get("class", "").endswith("-matrix")
    )
    borders = [text for text in matrix if text.text and set(text.text) <= FRAME_GLYPHS]
    top = next(text for text in borders if text.text and text.text.startswith("╔"))
    bottom = next(text for text in borders if text.text and text.text.startswith("╚"))
    cell_width = float(top.get("textLength", 0)) / len(top.text or "")
    left = float(top.get("x", 0)) + cell_width / 2
    width = float(top.get("textLength", 0)) - cell_width
    top_center = _row_center(top)
    height = _row_center(bottom) - top_center
    color = _class_fill(root, top.get("class", ""))

    for text in borders:
        matrix.remove(text)
    for position, inset in enumerate((-FRAME_LINE_GAP / 2, FRAME_LINE_GAP / 2)):
        rect = ElementTree.Element(
            f"{SVG}rect",
            {
                "fill": "none",
                "stroke": color,
                "stroke-width": f"{FRAME_STROKE:g}",
                "x": f"{left + inset:g}",
                "y": f"{top_center + inset:g}",
                "width": f"{width - 2 * inset:g}",
                "height": f"{height - 2 * inset:g}",
            },
        )
        matrix.insert(position, rect)

    ElementTree.register_namespace("", SVG_NAMESPACE)
    ElementTree.indent(root, space="    ")
    return ElementTree.tostring(root, encoding="unicode")


def _row_center(text: ElementTree.Element) -> float:
    return float(text.get("y", 0)) - SVG_BASELINE + SVG_LINE_OFFSET + SVG_LINE_HEIGHT / 2


def _class_fill(root: ElementTree.Element, class_name: str) -> str:
    style = root.find(f"{SVG}style")
    styles = style.text if style is not None and style.text else ""
    match = re.search(rf"\.{re.escape(class_name)} {{ fill: (#[0-9a-fA-F]+)", styles)
    if match is None:
        raise ValueError(f"No fill color was found for SVG class {class_name}")
    return match.group(1)


def _new_banner(banner_type: type[Banner]) -> Banner:
    no_color = os.environ.pop("NO_COLOR", None)
    try:
        return banner_type()
    finally:
        if no_color is not None:
            os.environ["NO_COLOR"] = no_color


def main() -> None:
    paths = asyncio.run(generate_banner())
    for path in paths:
        print(f"Generated {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
