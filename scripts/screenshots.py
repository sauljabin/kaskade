import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from textual.app import ComposeResult
from textual.widgets import Footer

from kaskade.admin import KaskadeAdmin, ListTopics
from kaskade.configs import BOOTSTRAP_SERVERS
from kaskade.consumer import KaskadeConsumer, ListRecords
from kaskade.deserializers import Deserialization, DeserializerPool, StringDeserializer
from kaskade.models import (
    Group,
    GroupMember,
    GroupPartition,
    Header,
    MetricState,
    Partition,
    Record,
    Topic,
)
from kaskade.services import ConsumerService, EnrichmentResult, GroupSnapshot, TopicService
from kaskade.widgets import KaskadeHeader
from scripts.svg import normalize_svg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGES_DIRECTORY = PROJECT_ROOT / "images"
SCREENSHOT_SIZE = (100, 30)
KAFKA_CONFIG = {BOOTSTRAP_SERVERS: "kafka.example.com:9092"}


def _partitions(topic: str, count: int, records: int) -> list[Partition]:
    return [
        Partition(
            id=partition_id,
            leader=partition_id % 3,
            replicas=[0, 1, 2],
            isrs=[0, 1, 2],
            low=0,
            high=records // count,
            topic=topic,
        )
        for partition_id in range(count)
    ]


def _group(topic: str, name: str, lag: int, members: int = 2) -> Group:
    return Group(
        id=name,
        members=[
            GroupMember(id=f"{name}-{member_id}", group=name) for member_id in range(1, members + 1)
        ],
        partitions=[
            GroupPartition(id=0, topic=topic, group=name, offset=10_000 - lag, high=10_000)
        ],
    )


def mock_topics() -> dict[str, Topic]:
    """Build stable, representative admin data without a Kafka broker."""
    topic_specs: tuple[tuple[str, int, int, list[Group]], ...] = (
        ("customer-events", 12, 184_320, [_group("customer-events", "analytics", 18)]),
        ("inventory-updates", 6, 72_408, [_group("inventory-updates", "warehouse", 0)]),
        ("order-events", 12, 391_024, [_group("order-events", "fulfillment", 42, 3)]),
        ("payment-events", 9, 128_906, [_group("payment-events", "fraud-detection", 7)]),
        ("shipping-status", 6, 83_115, [_group("shipping-status", "notifications", 3)]),
        ("user-notifications", 3, 24_901, []),
    )
    return {
        name: Topic(
            name=name,
            partitions=_partitions(name, partition_count, records),
            groups=groups,
            records_state=MetricState.READY,
            groups_state=MetricState.READY,
        )
        for name, partition_count, records, groups in topic_specs
    }


class MockTopicService(TopicService):
    def __init__(self) -> None:
        pass

    async def metadata(self) -> dict[str, Topic]:
        return mock_topics()

    async def enrich_offsets(self, topics: dict[str, Topic]) -> EnrichmentResult:
        return EnrichmentResult()

    async def load_groups(self) -> GroupSnapshot:
        return GroupSnapshot()

    def apply_groups(
        self, topics: dict[str, Topic], groups_snapshot: GroupSnapshot
    ) -> EnrichmentResult:
        return EnrichmentResult()


class AdminScreenshotApp(KaskadeAdmin):
    CSS_PATH = str(PROJECT_ROOT / "kaskade" / "styles.css")

    def compose(self) -> ComposeResult:
        yield KaskadeHeader(self.kafka_config)
        yield ListTopics(MockTopicService())
        yield Footer(compact=True)

    def admin_refresh_completed(self) -> None:
        super().admin_refresh_completed()
        topics = self.query_one(ListTopics)
        topics.last_updated_at = datetime(2026, 8, 28, 14, 30, tzinfo=timezone.utc)
        topics._update_status(refreshing=False)


def mock_records() -> list[Record]:
    """Build stable, representative consumer data without a Kafka broker."""
    string_deserializer = StringDeserializer()
    values = (
        ("order-1048", '{"customer":"Ada","total":149.90,"status":"paid"}'),
        ("order-1049", '{"customer":"Linus","total":42.00,"status":"paid"}'),
        ("order-1050", '{"customer":"Grace","total":87.35,"status":"pending"}'),
        ("order-1051", '{"customer":"Edsger","total":215.10,"status":"paid"}'),
        ("order-1052", '{"customer":"Margaret","total":63.80,"status":"shipped"}'),
        ("order-1053", '{"customer":"Barbara","total":19.99,"status":"paid"}'),
        ("order-1054", '{"customer":"Ken","total":104.25,"status":"pending"}'),
        ("order-1055", '{"customer":"James","total":78.45,"status":"shipped"}'),
    )
    return [
        Record(
            topic="order-events",
            partition=index % 3,
            offset=8_421 + index,
            date=f"2026-08-28 14:{12 + index:02d}:05.120",
            key=key.encode(),
            value=value.encode(),
            headers=[
                Header(key="source", value=b"storefront", value_deserializer=string_deserializer)
            ],
            key_deserialization=Deserialization.STRING,
            value_deserialization=Deserialization.STRING,
            key_deserializer=string_deserializer,
            value_deserializer=string_deserializer,
        )
        for index, (key, value) in enumerate(values)
    ]


class MockConsumerService(ConsumerService):
    def __init__(self) -> None:
        self.page_size = 25
        self._records = mock_records()

    async def consume(
        self,
        *,
        partition_filter: int | None = None,
        key_filter: str | None = None,
        value_filter: str | None = None,
        header_filter: str | None = None,
    ) -> list[Record]:
        records, self._records = self._records, []
        return records

    def close(self) -> None:
        pass


class ScreenshotRecords(ListRecords):
    def _new_consumer(self) -> ConsumerService:
        return MockConsumerService()


class ConsumerScreenshotApp(KaskadeConsumer):
    CSS_PATH = str(PROJECT_ROOT / "kaskade" / "styles.css")

    def compose(self) -> ComposeResult:
        yield KaskadeHeader(self.kafka_config)
        yield ScreenshotRecords(
            self.topic,
            self.kafka_config,
            DeserializerPool(),
            self.key_deserialization,
            self.value_deserialization,
        )
        yield Footer(compact=True)


async def _export(app: KaskadeAdmin | KaskadeConsumer, filename: str) -> Path:
    async with app.run_test(size=SCREENSHOT_SIZE) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        svg = app.export_screenshot(title=app.TITLE, simplify=True)

    path = IMAGES_DIRECTORY / filename
    path.write_text(normalize_svg(svg), encoding="utf-8")
    return path


async def generate_screenshots() -> tuple[Path, Path]:
    """Render admin and consumer README screenshots as SVG files."""
    IMAGES_DIRECTORY.mkdir(parents=True, exist_ok=True)
    admin, consumer = _new_apps()
    admin_path = await _export(admin, "admin.svg")
    consumer_path = await _export(consumer, "consumer.svg")
    return admin_path, consumer_path


def _new_apps() -> tuple[AdminScreenshotApp, ConsumerScreenshotApp]:
    no_color = os.environ.pop("NO_COLOR", None)
    try:
        return AdminScreenshotApp(KAFKA_CONFIG, refresh_interval=0), ConsumerScreenshotApp(
            "order-events",
            KAFKA_CONFIG,
            {},
            {},
            {},
            Deserialization.STRING,
            Deserialization.STRING,
        )
    finally:
        if no_color is not None:
            os.environ["NO_COLOR"] = no_color


def main() -> None:
    paths = asyncio.run(generate_screenshots())
    for path in paths:
        print(f"Generated {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
