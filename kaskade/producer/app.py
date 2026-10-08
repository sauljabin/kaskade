"""The Kaskade producer application."""

from textual.app import ComposeResult
from textual.widgets import Footer

from kaskade.app import KaskadeApp
from kaskade.producer.composer import RecordComposer
from kaskade.producer.source import RecordDraft
from kaskade.producer_service import ProducerService, ProducerSettings
from kaskade.settings import AppSettings
from kaskade.widgets import KaskadeHeader, kantrip_profile


class KaskadeProducer(KaskadeApp):
    TITLE = "Kaskade Producer"
    AUTO_FOCUS = "#composer-tabs Tabs"

    def __init__(
        self,
        producer_settings: ProducerSettings,
        *,
        drafts: tuple[RecordDraft, ...] = (),
        settings: AppSettings | None = None,
    ) -> None:
        super().__init__(settings=settings)
        self.producer_settings = producer_settings
        self.drafts = drafts
        self.producer = ProducerService(producer_settings)
        self.producer.start()

    def compose(self) -> ComposeResult:
        yield KaskadeHeader(self.producer_settings.kafka_config, profile=kantrip_profile())
        yield RecordComposer(self.producer_settings, self.producer, self.drafts)
        yield Footer(compact=True)
