"""Record the site's admin, consumer, and producer demos from the real apps.

Each scene drives a mode with Pilot over the screenshot mock data and keeps
every screen as text: lines of HTML runs whose colors are CSS classes. The
site replays those frames, so it shows exactly what Kaskade draws.
"""

import asyncio
import html
import json
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from itertools import groupby
from pathlib import Path
from typing import Any
from unittest.mock import patch
from xml.etree import ElementTree

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.pilot import Pilot
from textual.widgets import Footer

from kaskade.admin import ListTopics
from kaskade.commands import EMPTY_RECORD_FILTERS, RecordFilters
from kaskade.consumer_service import ConsumerService, ConsumerSettings
from kaskade.deserializers import Deserialization
from kaskade.models import MetricState, Record, Topic, TopicConfiguration
from kaskade.producer_service import Delivery, OutgoingRecord, ProducerService, ProducerSettings
from kaskade.serializers import Serialization
from kaskade.settings import AppSettings
from kaskade.themes import EVA01_BERSERK_THEME
from kaskade.topic_service import EnrichmentResult, GroupSnapshot
from kaskade.widgets import KaskadeHeader
from scripts import (
    BLOCK_GLYPHS,
    BOX_GLYPHS,
    SVG,
    SVG_BASELINE,
    SVG_CELL_WIDTH,
    SVG_LINE_HEIGHT,
    SVG_LINE_OFFSET,
    screenshots,
)
from scripts.screenshots import (
    KAFKA_CONFIG,
    PRODUCER_DRAFT,
    PROJECT_ROOT,
    AdminScreenshotApp,
    ConsumerScreenshotApp,
    MockConsumerService,
    MockProducerService,
    MockTopicService,
    ProducerScreenshotApp,
    mock_topics,
)

SITE_DIRECTORY = PROJECT_ROOT / "site"
DEMOS_PATH = SITE_DIRECTORY / "demos.json"
DEMOS_CSS_PATH = SITE_DIRECTORY / "demos.css"
INDEX_PATH = SITE_DIRECTORY / "index.html"
DEMO_SIZE = (100, 30)
# The header shows this in place of a version; the site fills in the latest
# release, padded to the same width.
VERSION_PLACEHOLDER = "X.Y.Z"
VERSION_TEXT = f"v{VERSION_PLACEHOLDER}"
SVG_STYLE_RULE = re.compile(r"\.([\w-]+) \{ ([^}]*) \}")


def _box_arms(horizontal: int, vertical: int) -> str:
    """Translate a README box glyph's arms; a straight line has no arm on the other axis."""
    if vertical == 0:
        return "lr"
    if horizontal == 0:
        return "ud"
    return ("l" if horizontal < 0 else "r") + ("u" if vertical < 0 else "d")


# Light, heavy, and half lines: the arms each glyph draws from its center, and
# whether they are heavy. Box glyphs already drawn as paths in the README
# screenshots share their arms.
LINE_GLYPHS: dict[str, tuple[str, bool]] = {
    **{glyph: (_box_arms(h, v), double) for glyph, (h, v, double) in BOX_GLYPHS.items()},
    "╭": ("rd", False),
    "╮": ("ld", False),
    "╰": ("ru", False),
    "╯": ("lu", False),
    "━": ("lr", True),
    "┃": ("ud", True),
    "╸": ("l", True),
    "╺": ("r", True),
    "╴": ("l", False),
    "╶": ("r", False),
}
# Block glyphs fill these fractions of the cell: left, right, top, bottom.
FILL_GLYPHS: dict[str, tuple[float, float, float, float]] = {
    **{glyph: (start, end, 0, 1) for glyph, (start, end) in BLOCK_GLYPHS.items()},
    "█": (0, 1, 0, 1),
    "▀": (0, 1, 0, 0.5),
    "▄": (0, 1, 0.5, 1),
    "▔": (0, 1, 0, 0.125),
    "▁": (0, 1, 0.875, 1),
}
DRAWING_RANGE = range(0x2500, 0x25A0)
# The site's window paints the theme background, so runs leave it out.
SCREEN_BACKGROUND = (EVA01_BERSERK_THEME.background or "").lower()


@dataclass(frozen=True)
class Cell:
    character: str
    style: tuple[str, ...]


@dataclass
class Frame:
    lines: list[str]
    delay: int
    key: str | None = None


@dataclass
class Scene:
    command: str
    frames: list[Frame] = field(default_factory=list)


class Recorder:
    """Keep each screen of a scene, with how long to show it and the key that led to it."""

    def __init__(self, pilot: Pilot[object], scene: Scene) -> None:
        self.pilot = pilot
        self.scene = scene

    async def capture(self, delay: int, key: str | None = None) -> None:
        await self.pilot.pause()
        self.scene.frames.append(
            Frame(screen_lines(self.pilot.app.export_screenshot()), delay, key)
        )

    async def press(self, key: str, label: str, delay: int, settle: float = 0) -> None:
        """Press a key; settle waits for animations such as a toast sliding in."""
        await self.pilot.press(key)
        await self.pilot.app.workers.wait_for_complete()
        await self.pilot.pause(settle or None)
        await self.capture(delay, label)


# Screen parsing: Rich exports a cell grid as background rectangles and text runs.


def screen_lines(svg: str) -> list[str]:
    """Convert a Textual SVG screenshot into HTML lines of styled runs."""
    return [line_html(row) for row in screen_cells(svg)]


def screen_cells(svg: str) -> list[list[Cell]]:
    root = ElementTree.fromstring(svg)
    matrix = next(
        group for group in root.iter(f"{SVG}g") if group.get("class", "").endswith("-matrix")
    )
    style = root.find(f"{SVG}style")
    rules = SVG_STYLE_RULE.findall(style.text or "" if style is not None else "")
    classes = {name: _declarations(rule) for name, rule in rules}
    columns, rows = DEMO_SIZE
    backgrounds: list[list[str | None]] = [[None] * columns for _ in range(rows)]
    for rect in root.iter(f"{SVG}rect"):
        if rect.get("shape-rendering") != "crispEdges" or not rect.get("fill"):
            continue
        row = round((float(rect.get("y", 0)) - SVG_LINE_OFFSET) / SVG_LINE_HEIGHT)
        start = round(float(rect.get("x", 0)) / SVG_CELL_WIDTH)
        width = round(float(rect.get("width", 0)) / SVG_CELL_WIDTH)
        for column in range(start, min(start + width, columns)):
            if 0 <= row < rows:
                backgrounds[row][column] = rect.get("fill")
    cells = [[Cell(" ", _style(None, background)) for background in line] for line in backgrounds]
    for text in matrix.iter(f"{SVG}text"):
        row = round((float(text.get("y", 0)) - SVG_BASELINE) / SVG_LINE_HEIGHT)
        column = round(float(text.get("x", 0)) / SVG_CELL_WIDTH)
        declarations = classes.get(text.get("class", ""), {})
        for character in (text.text or "").replace("\xa0", " "):
            if 0 <= row < rows and column < columns:
                cells[row][column] = Cell(character, _style(declarations, backgrounds[row][column]))
            column += cell_len(character)
    return cells


def _declarations(rule: str) -> dict[str, str]:
    pairs = (part.split(":", 1) for part in rule.split(";") if ":" in part)
    return {name.strip(): value.strip() for name, value in pairs}


def _style(declarations: dict[str, str] | None, background: str | None) -> tuple[str, ...]:
    declarations = declarations or {}
    style = []
    if "fill" in declarations:
        style.append(f"color:{declarations['fill']}")
    if background and background.lower() != SCREEN_BACKGROUND:
        style.append(f"background:{background}")
    if declarations.get("font-weight") == "bold":
        style.append("font-weight:700")
    if declarations.get("font-style") == "italic":
        style.append("font-style:italic")
    if "underline" in declarations.get("text-decoration", ""):
        style.append("text-decoration:underline")
    return tuple(style)


# HTML: runs share a CSS class per style, and drawing glyphs become cells drawn
# with CSS, never glyphs from a fallback font.

STYLE_CLASSES: dict[tuple[str, ...], str] = {}


def _style_class(style: tuple[str, ...]) -> str:
    return STYLE_CLASSES.setdefault(style, f"s{len(STYLE_CLASSES)}")


def line_html(cells: list[Cell]) -> str:
    runs = []
    for (glyph, style), group in groupby(cells, _run_key):
        characters = "".join(cell.character for cell in group)
        if glyph:
            runs.extend(_glyph_runs(glyph, style, len(characters)))
        else:
            runs.append(_run_html(characters, style))
    # Unstyled trailing spaces show nothing, and index.html keeps no trailing whitespace.
    line = "".join(runs).rstrip(" ")
    return line.replace(html.escape(VERSION_TEXT), "<span data-version>      </span>")


def _run_key(cell: Cell) -> tuple[str, tuple[str, ...]]:
    """Group text by style, and each drawing glyph with its repeats."""
    character = cell.character
    if character in LINE_GLYPHS or character in FILL_GLYPHS:
        return character, cell.style
    if ord(character) in DRAWING_RANGE:
        raise ValueError(f"no CSS drawing for {character!r} (U+{ord(character):04X})")
    return "", cell.style


def _run_html(text: str, style: tuple[str, ...]) -> str:
    if not style:
        return html.escape(text, quote=False)
    return f'<span class="{_style_class(style)}">{html.escape(text, quote=False)}</span>'


def _glyph_runs(glyph: str, style: tuple[str, ...], count: int) -> list[str]:
    """A horizontal line or a full-width fill stretches across its repeats."""
    classes = ["g", _style_class(style)] if style else ["g"]
    declarations = []
    if glyph in LINE_GLYPHS:
        arms, heavy = LINE_GLYPHS[glyph]
        classes += [f"g{arm}" for arm in arms] + (["gh"] if heavy else [])
        stretches = arms == "lr"
    else:
        left, right, top, bottom = FILL_GLYPHS[glyph]
        classes.append("gf")
        declarations = [
            f"--t:{top:g}",
            f"--r:{1 - right:g}",
            f"--b:{1 - bottom:g}",
            f"--l:{left:g}",
        ]
        stretches = (left, right) == (0, 1)
    widths = [count] if stretches else [1] * count
    return [_glyph_span(classes, declarations + [f"--n:{n}"] * (n > 1)) for n in widths]


def _glyph_span(classes: list[str], declarations: list[str]) -> str:
    style = f' style="{";".join(declarations)}"' if declarations else ""
    return f'<span class="{" ".join(classes)}"{style}></span>'


def styles_css() -> str:
    rules = "\n".join(f".{name} {{ {'; '.join(style)} }}" for style, name in STYLE_CLASSES.items())
    return f"/* Generated by scripts.demos from Kaskade's theme. */\n{rules}\n"


# Scenes: the screenshot apps, gated where the real app waits on Kafka.


class DemoTopicService(MockTopicService):
    """Topic metadata arrives first; record and group metrics wait for the gate."""

    def __init__(self, gate: asyncio.Event) -> None:
        self.gate = gate

    async def metadata(self) -> dict[str, Topic]:
        return {
            name: replace(
                topic, records_state=MetricState.LOADING, groups_state=MetricState.LOADING
            )
            for name, topic in mock_topics().items()
        }

    async def enrich_offsets(self, topics: dict[str, Topic]) -> EnrichmentResult:
        await self.gate.wait()
        for topic in topics.values():
            topic.records_state = MetricState.READY
        return EnrichmentResult()

    async def load_groups(self) -> GroupSnapshot:
        await self.gate.wait()
        return GroupSnapshot()

    def apply_groups(
        self, topics: dict[str, Topic], groups_snapshot: GroupSnapshot
    ) -> EnrichmentResult:
        for topic in topics.values():
            topic.groups_state = MetricState.READY
        return EnrichmentResult()

    def describe_configs(self, name: str) -> tuple[TopicConfiguration, ...]:
        return (
            TopicConfiguration("cleanup.policy", "delete"),
            TopicConfiguration("min.insync.replicas", "2"),
            TopicConfiguration("retention.ms", "604800000"),
        )


class AdminDemoApp(AdminScreenshotApp):
    def __init__(self) -> None:
        super().__init__(KAFKA_CONFIG, settings=AppSettings(path=Path(), keymap={}))
        self.gate = asyncio.Event()

    def compose(self) -> ComposeResult:
        yield KaskadeHeader(self.kafka_config, version=VERSION_PLACEHOLDER)
        yield ListTopics(DemoTopicService(self.gate), refresh_interval=self.auto_refresh_interval)
        yield Footer(compact=True)


class GatedConsumerService(MockConsumerService):
    """Records arrive when the gate opens, like a first fetch from a slow broker."""

    def __init__(self, gate: asyncio.Event) -> None:
        super().__init__()
        self.gate = gate

    async def consume(self, *, filters: RecordFilters = EMPTY_RECORD_FILTERS) -> list[Record]:
        await self.gate.wait()
        return await super().consume(filters=filters)


class ConsumerDemoApp(ConsumerScreenshotApp):
    def __init__(self) -> None:
        self.gate = asyncio.Event()
        super().__init__(
            ConsumerSettings(
                "order-events", KAFKA_CONFIG, Deserialization.STRING, Deserialization.STRING
            ),
            settings=AppSettings(path=Path(), keymap={}),
        )

    def new_consumer(self) -> ConsumerService:
        return GatedConsumerService(self.gate)


class DeliveringProducerService(MockProducerService):
    async def produce(self, record: OutgoingRecord) -> Delivery:
        delivered_at = datetime(2026, 8, 28, 14, 20, 5, 120_000).astimezone()
        return Delivery(partition=4, offset=32_585, timestamp=delivered_at)


class ProducerDemoApp(ProducerScreenshotApp):
    def __init__(self) -> None:
        super().__init__(
            ProducerSettings(
                "order-events", KAFKA_CONFIG, Serialization.STRING, Serialization.JSON
            ),
            draft=PRODUCER_DRAFT,
            settings=AppSettings(path=Path(), keymap={}),
        )

    def new_producer(self) -> ProducerService:
        return DeliveringProducerService(self.producer_settings)


async def record_admin(app: AdminDemoApp, recorder: Recorder) -> None:
    await recorder.capture(1100)
    app.gate.set()
    await app.workers.wait_for_complete()
    await recorder.capture(1300)
    await recorder.press("j", "j", 500)
    await recorder.press("j", "j", 900)
    await recorder.press("d", "d", 3800)
    await recorder.press("escape", "esc", 900)


async def record_consumer(app: ConsumerDemoApp, recorder: Recorder) -> None:
    await recorder.capture(1000)
    app.gate.set()
    await app.workers.wait_for_complete()
    await recorder.capture(1500)
    await recorder.press("j", "j", 500)
    await recorder.press("j", "j", 900)
    await recorder.press("enter", "⏎", 3800)
    await recorder.press("escape", "esc", 900)


async def record_producer(app: ProducerDemoApp, recorder: Recorder) -> None:
    await recorder.capture(2400)
    await recorder.press("ctrl+s", "^s", 3800, settle=0.5)


SCENES: dict[str, tuple[str, Callable[[], Any], Callable[[Any, Recorder], Awaitable[None]]]] = {
    "admin": ("kaskade admin -b kafka.example.com:9092", AdminDemoApp, record_admin),
    "consumer": (
        "kaskade consumer -b kafka.example.com:9092 -t order-events",
        ConsumerDemoApp,
        record_consumer,
    ),
    "producer": (
        "kaskade producer -b kafka.example.com:9092 -t order-events -v json --source order.json",
        ProducerDemoApp,
        record_producer,
    ),
}


async def record_scenes() -> dict[str, Scene]:
    """Record every scene with fresh style classes, so output is deterministic."""
    STYLE_CLASSES.clear()
    scenes = {}
    # Screenshot apps put the version in their header; the site fills in the release.
    # NO_COLOR would record the frames without the theme.
    with (
        patch.object(screenshots, "SCREENSHOT_VERSION", VERSION_PLACEHOLDER),
        patch.dict(os.environ),
    ):
        os.environ.pop("NO_COLOR", None)
        for name, (command, new_app, steps) in SCENES.items():
            scene = Scene(command)
            app = new_app()
            # Animated widgets, such as the loading indicator's dots, change color
            # with the clock; without animation every recording is identical.
            app.animation_level = "none"
            async with app.run_test(size=DEMO_SIZE, notifications=True) as pilot:
                await steps(app, Recorder(pilot, scene))
            scenes[name] = scene
    return scenes


def demos_json(scenes: dict[str, Scene]) -> str:
    """Store each distinct line once; frames list line indexes."""
    lines: dict[str, int] = {}
    demos = {
        name: {
            "frames": [
                {
                    "lines": [lines.setdefault(line, len(lines)) for line in frame.lines],
                    "delay": frame.delay,
                    **({"key": frame.key} if frame.key else {}),
                }
                for frame in scene.frames
            ],
        }
        for name, scene in scenes.items()
    }
    return json.dumps({"lines": list(lines), "demos": demos}, ensure_ascii=False) + "\n"


def render_index(index: str, scenes: dict[str, Scene]) -> str:
    """Write each scene's command and last frame between its markers in index.html.

    Visitors without JavaScript see that frame; the replay starts from it.
    """
    for name, scene in scenes.items():
        start, end = f"<!-- demo:{name}:start -->", f"<!-- demo:{name}:end -->"
        before, rest = index.split(start, 1)
        _, after = rest.split(end, 1)
        screen = (
            '\n<pre class="shell" aria-hidden="true"><code><span class="t-prompt">\u276f </span>'
            f"<span data-shell-command>{html.escape(scene.command)}</span></code></pre>\n"
            '<pre class="tui" data-frame>' + "\n".join(scene.frames[-1].lines) + "</pre>\n"
        )
        index = before + start + screen + end + after
    return index


def generate_demos() -> tuple[Path, ...]:
    scenes = asyncio.run(record_scenes())
    DEMOS_PATH.write_text(demos_json(scenes), encoding="utf-8")
    DEMOS_CSS_PATH.write_text(styles_css(), encoding="utf-8")
    INDEX_PATH.write_text(render_index(INDEX_PATH.read_text(encoding="utf-8"), scenes), "utf-8")
    return DEMOS_PATH, DEMOS_CSS_PATH, INDEX_PATH


def main() -> None:
    for path in generate_demos():
        print(f"Generated {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
