import asyncio
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from textual.app import ComposeResult

from kaskade.banner import KaskadeBanner
from kaskade.themes import KaskadeApp

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGES_DIRECTORY = PROJECT_ROOT / "images"
BANNER_PATH = IMAGES_DIRECTORY / "banner.svg"
BANNER_SIZE = (42, 8)


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


async def generate_banner() -> Path:
    """Render the README banner with Textual's SVG screenshot exporter."""
    with _color_enabled():
        app = Banner()
        async with app.run_test(size=BANNER_SIZE) as pilot:
            await pilot.pause()
            svg = app.export_screenshot(title="Kaskade", simplify=True)

    IMAGES_DIRECTORY.mkdir(parents=True, exist_ok=True)
    BANNER_PATH.write_text(_normalize_svg(svg), encoding="utf-8")
    return BANNER_PATH


def _normalize_svg(svg: str) -> str:
    return "\n".join(line.rstrip() for line in svg.splitlines()) + "\n"


@contextmanager
def _color_enabled() -> Iterator[None]:
    no_color = os.environ.pop("NO_COLOR", None)
    try:
        yield
    finally:
        if no_color is not None:
            os.environ["NO_COLOR"] = no_color


def main() -> None:
    path = asyncio.run(generate_banner())
    print(f"Generated {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
