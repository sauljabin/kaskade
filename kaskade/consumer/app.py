"""The Kaskade consumer application."""

from textual.app import ComposeResult
from textual.widgets import Footer

from kaskade.app import KaskadeApp
from kaskade.consumer.records import ListRecords
from kaskade.consumer_service import ConsumerService, ConsumerSettings
from kaskade.widgets import KaskadeHeader, kantrip_profile


class KaskadeConsumer(KaskadeApp):
    TITLE = "Kaskade Consumer"
    AUTO_FOCUS = "#records-table"

    def __init__(self, settings: ConsumerSettings) -> None:
        super().__init__()
        self.consumer_settings = settings
        self.deserializer_pool = settings.deserializer_pool()
        self.consumer = self.new_consumer()
        try:
            self.consumer.start()
        except Exception:
            self.consumer.close()
            raise

    def new_consumer(self) -> ConsumerService:
        """Build a consumer from the settings; filter changes build a fresh one."""
        return ConsumerService(self.consumer_settings, self.deserializer_pool)

    def compose(self) -> ComposeResult:
        yield KaskadeHeader(self.consumer_settings.kafka_config, profile=kantrip_profile())
        yield ListRecords(
            self.consumer_settings.topic,
            self.new_consumer,
            self.deserializer_pool,
            consumer=self.consumer,
        )
        yield Footer(compact=True)
