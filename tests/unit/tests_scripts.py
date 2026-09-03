import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

from kaskade import APP_VERSION
from kaskade.themes import EVA01_BERSERK_THEME
from scripts import banner, screenshots


class TestReadmeVisualScripts(unittest.IsolatedAsyncioTestCase):
    def assert_default_theme_colors(self, svg: str) -> None:
        secondary = EVA01_BERSERK_THEME.secondary
        self.assertIsNotNone(secondary)
        assert secondary is not None
        self.assertIn(EVA01_BERSERK_THEME.primary.lower(), svg)
        self.assertIn(secondary.lower(), svg)

    def assert_intrinsic_dimensions(self, svg: str) -> None:
        root = ElementTree.fromstring(svg)
        _, _, view_width, view_height = root.attrib["viewBox"].split()
        self.assertEqual(view_width, root.attrib["width"])
        self.assertEqual(view_height, root.attrib["height"])

    async def test_banner_generates_framed_and_borderless_default_theme_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            with (
                patch.dict(os.environ, {"NO_COLOR": "1"}),
                patch.object(banner, "IMAGES_DIRECTORY", output),
                patch.object(banner, "BANNER_PATH", output / "banner.svg"),
                patch.object(banner, "BORDERLESS_BANNER_PATH", output / "banner-borderless.svg"),
            ):
                paths = await banner.generate_banner()

            self.assertEqual({path.name for path in paths}, {"banner.svg", "banner-borderless.svg"})
            for path in paths:
                with self.subTest(path=path.name):
                    svg = path.read_text(encoding="utf-8")
                    self.assert_default_theme_colors(svg.lower())
                    self.assert_intrinsic_dimensions(svg)
                    self.assertIn("╗", svg)
                    self.assertIn("╝", svg)
                    circles = sum(
                        child.tag.endswith("circle") for child in ElementTree.fromstring(svg).iter()
                    )
                    self.assertEqual(circles, 0 if "borderless" in path.stem else 3)

            borderless_svg = paths[1].read_text(encoding="utf-8").lower()
            self.assertIn(EVA01_BERSERK_THEME.background.lower(), borderless_svg)

    async def test_screenshots_generate_framed_and_borderless_default_theme_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            with (
                patch.dict(os.environ, {"NO_COLOR": "1"}),
                patch.object(screenshots, "IMAGES_DIRECTORY", output),
            ):
                paths = await screenshots.generate_screenshots()

            self.assertEqual(
                {path.name for path in paths},
                {
                    "admin.svg",
                    "admin-borderless.svg",
                    "consumer.svg",
                    "consumer-borderless.svg",
                },
            )
            for path in paths:
                with self.subTest(path=path.name):
                    svg = path.read_text(encoding="utf-8")
                    self.assert_default_theme_colors(svg.lower())
                    self.assert_intrinsic_dimensions(svg)
                    self.assertIn(f"v{screenshots.SCREENSHOT_VERSION}", svg)
                    if APP_VERSION != screenshots.SCREENSHOT_VERSION:
                        self.assertNotIn(f"v{APP_VERSION}", svg)

                    root = ElementTree.fromstring(svg)
                    terminal_groups = [
                        child
                        for child in root
                        if child.tag.endswith("g") and "clip-terminal" in child.get("clip-path", "")
                    ]
                    self.assertEqual(len(terminal_groups), 1)
                    if "borderless" in path.stem:
                        self.assertNotIn("transform", terminal_groups[0].attrib)
                        self.assertFalse(any(child.tag.endswith("circle") for child in root.iter()))
                    else:
                        self.assertIn("transform", terminal_groups[0].attrib)
                        self.assertEqual(
                            sum(child.tag.endswith("circle") for child in root.iter()), 3
                        )
