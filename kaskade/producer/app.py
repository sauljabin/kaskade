"""The Kaskade producer application."""

from confluent_kafka.serialization import MessageField
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
        draft: RecordDraft | None = None,
        settings: AppSettings | None = None,
    ) -> None:
        super().__init__(settings=settings)
        self.producer_settings = producer_settings
        self.draft = draft
        self.producer = self.new_producer()
        self.producer.start()
        # Build the serializers now, so unusable schema files or Registry settings
        # fail before the TUI opens; Registry schemas are looked up once it runs.
        self.serializers = producer_settings.serializer_pool()
        try:
            self.field_serializers = {
                "key": self.serializers.get(producer_settings.key_serialization, MessageField.KEY),
                "value": self.serializers.get(
                    producer_settings.value_serialization, MessageField.VALUE
                ),
            }
        except Exception:
            self.serializers.close()
            raise

    def new_producer(self) -> ProducerService:
        return ProducerService(self.producer_settings)

    def compose(self) -> ComposeResult:
        yield KaskadeHeader(self.producer_settings.kafka_config, profile=kantrip_profile())
        yield RecordComposer(
            self.producer_settings,
            self.producer,
            self.serializers,
            self.field_serializers,
            self.draft,
        )
        yield Footer(compact=True)
