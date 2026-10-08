from concurrent.futures import Future
from unittest.mock import AsyncMock, MagicMock

from faker import Faker

from kaskade.models import MetricState, Record, Topic
from kaskade.topic_service import EnrichmentResult, GroupSnapshot

faker = Faker()


def completed(value: object) -> Future[object]:
    future: Future[object] = Future()
    future.set_result(value)
    return future


def failed(error: Exception) -> Future[object]:
    future: Future[object] = Future()
    future.set_exception(error)
    return future


def configure_consumer_service(service: MagicMock, records: list[Record] | None = None) -> None:
    """Make a consumer service double consume the records and close asynchronously."""
    service.consume = AsyncMock(return_value=records or [])
    service.aclose = AsyncMock()
    service.group_id = ""


def configure_admin_service(service: MagicMock, topics: dict[str, Topic]) -> None:
    for topic in topics.values():
        topic.records_state = MetricState.READY
        topic.groups_state = MetricState.READY
    service.metadata = AsyncMock(return_value=topics)
    service.enrich_offsets = AsyncMock(return_value=EnrichmentResult())
    service.load_groups = AsyncMock(return_value=GroupSnapshot())
    service.apply_groups.return_value = EnrichmentResult()
    service.describe_configs.return_value = ()
