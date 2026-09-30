import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

import yaml

from kaskade import APP_VERSION
from kaskade.themes import EVA01_BERSERK_THEME
from scripts import BOX_GLYPHS, banner, draw_box_glyphs, screenshots


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

    def assert_box_glyphs_drawn(self, svg: str, color: str) -> None:
        self.assertFalse(BOX_GLYPHS.keys() & set(svg))
        strokes = {
            element.get("stroke", "").lower()
            for element in ElementTree.fromstring(svg).iter()
            if element.tag.endswith("path")
        }
        self.assertIn(color.lower(), strokes)

    def test_draw_box_glyphs_draws_paths_and_keeps_text_on_the_cell_grid(self) -> None:
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg"><style>.t-r1 { fill: #9b4dca }</style>'
            '<g class="t-matrix"><text class="t-r1" x="0" y="20" textLength="48.8">┌─ a</text>'
            "</g></svg>"
        )

        root = ElementTree.fromstring(draw_box_glyphs(svg))

        texts = [element for element in root.iter() if element.tag.endswith("text")]
        path = next(element for element in root.iter() if element.tag.endswith("path"))
        self.assertEqual(
            [(text.get("x"), text.get("textLength"), text.text) for text in texts],
            [("24.4", "24.4", " a")],
        )
        self.assertEqual(path.get("stroke"), "#9b4dca")
        self.assertEqual(path.get("d"), "M12.2 13.7H6.1V25.9M12.2 13.7H24.4")

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
                    self.assert_box_glyphs_drawn(svg, EVA01_BERSERK_THEME.primary)
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
                    self.assertFalse(BOX_GLYPHS.keys() & set(svg))
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

            consumer_svg = (output / "consumer.svg").read_text(encoding="utf-8")
            self.assertIn("Group&#160;order-inspector", consumer_svg)


ROOT = Path(__file__).resolve().parents[2]


def e2e_exempt_patterns() -> tuple[str, str]:
    hooks = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hook = next(
        hook for repo in hooks["repos"] for hook in repo["hooks"] if hook["id"] == "tests-e2e"
    )
    workflow = yaml.safe_load((ROOT / ".github/workflows/main.yml").read_text(encoding="utf-8"))
    step = next(
        step for step in workflow["jobs"]["e2e-selection"]["steps"] if step.get("id") == "select"
    )
    return hook["exclude"], step["env"]["E2E_EXEMPT"]


class TestE2ESelection(unittest.TestCase):
    def test_pre_push_hook_and_ci_skip_the_same_paths(self) -> None:
        hook_pattern, ci_pattern = e2e_exempt_patterns()
        self.assertEqual(hook_pattern, ci_pattern)

    def test_only_documentation_paths_skip_e2e(self) -> None:
        pattern = re.compile(e2e_exempt_patterns()[0])
        skipped = [
            "README.md",
            "USAGE.md",
            "LICENSE",
            "cliff.toml",
            "examples/client.ini",
            "images/banner.svg",
            "site/index.html",
            ".github/PULL_REQUEST_TEMPLATE/pull_request.md",
            ".github/workflows/pages.yml",
        ]
        selected = [
            "kaskade/main.py",
            "tests/e2e/tests_e2e.py",
            "scripts/tests.py",
            "sandbox/__main__.py",
            "pyproject.toml",
            "uv.lock",
            ".pre-commit-config.yaml",
            ".github/workflows/main.yml",
            "kaskade/readme.md.py",
        ]
        for path in skipped:
            self.assertIsNotNone(pattern.search(path), path)
        for path in selected:
            self.assertIsNone(pattern.search(path), path)
