import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kaskade.themes import EVA01_THEME
from scripts import banner, screenshots


class TestReadmeVisualScripts(unittest.IsolatedAsyncioTestCase):
    def assert_eva01_colors(self, svg: str) -> None:
        secondary = EVA01_THEME.secondary
        self.assertIsNotNone(secondary)
        assert secondary is not None
        self.assertIn(EVA01_THEME.primary.lower(), svg)
        self.assertIn(secondary.lower(), svg)

    async def test_banner_uses_eva01_colors_and_keeps_both_borders(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "banner.svg"
            with (
                patch.dict(os.environ, {"NO_COLOR": "1"}),
                patch.object(banner, "IMAGES_DIRECTORY", output.parent),
                patch.object(banner, "BANNER_PATH", output),
            ):
                await banner.generate_banner()

            svg = output.read_text(encoding="utf-8").lower()
            self.assert_eva01_colors(svg)
            self.assertIn("╗", svg)
            self.assertIn("╝", svg)

    async def test_screenshots_use_eva01_colors_when_no_color_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            with (
                patch.dict(os.environ, {"NO_COLOR": "1"}),
                patch.object(screenshots, "IMAGES_DIRECTORY", output),
            ):
                admin_path, consumer_path = await screenshots.generate_screenshots()

            for path in (admin_path, consumer_path):
                with self.subTest(path=path.name):
                    svg = path.read_text(encoding="utf-8").lower()
                    self.assert_eva01_colors(svg)
