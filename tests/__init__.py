from unittest.mock import AsyncMock, MagicMock

from faker import Faker

from kaskade.models import MetricState, Topic
from kaskade.services import EnrichmentResult, GroupSnapshot

faker = Faker()


def configure_admin_service(service: MagicMock, topics: dict[str, Topic]) -> None:
    for topic in topics.values():
        topic.records_state = MetricState.READY
        topic.groups_state = MetricState.READY
    service.metadata = AsyncMock(return_value=topics)
    service.enrich_offsets = AsyncMock(return_value=EnrichmentResult())
    service.load_groups = AsyncMock(return_value=GroupSnapshot())
    service.apply_groups.return_value = EnrichmentResult()
