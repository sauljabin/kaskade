import asyncio
import os
from pathlib import Path

from textual.app import ComposeResult

from kaskade.banner import KaskadeBanner
from kaskade.themes import KaskadeApp
from scripts import normalize_svg, remove_svg_terminal_chrome

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGES_DIRECTORY = PROJECT_ROOT / "images"
BANNER_PATH = IMAGES_DIRECTORY / "banner.svg"
BORDERLESS_BANNER_PATH = IMAGES_DIRECTORY / "banner-borderless.svg"
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
    framed_svg = await _render(_new_banner(Banner))
    borderless_svg = await _render(_new_banner(BorderlessBanner))

    IMAGES_DIRECTORY.mkdir(parents=True, exist_ok=True)
    BANNER_PATH.write_text(normalize_svg(framed_svg), encoding="utf-8")
    BORDERLESS_BANNER_PATH.write_text(
        normalize_svg(remove_svg_terminal_chrome(borderless_svg)), encoding="utf-8"
    )
    return BANNER_PATH, BORDERLESS_BANNER_PATH


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
