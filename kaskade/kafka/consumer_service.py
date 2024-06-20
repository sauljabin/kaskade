import uuid
from datetime import datetime
from typing import List

from confluent_kafka import Consumer, Message

from kaskade.config import Config
from kaskade.kafka.models import Record, Topic
from kaskade.kafka.schema_service import AVRO, SchemaService
from kaskade.kafka.schema_utils import deserialize_avro, unpack_schema_id

CONSUMER_TIMEOUT = 0.5

MAX_RETRIES_BEFORE_LEAVE = 10


class ConsumerService:
    def __init__(self, config: Config, topic: Topic) -> None:
        if config is None or config.kafka is None:
            raise Exception("Kafka config not found")
        self.config = config
        self.kafka_config = self.config.kafka.copy()
        self.kafka_config["group.id"] = "kaskade-" + str(uuid.uuid4())[:8]
        self.kafka_config["auto.offset.reset"] = "earliest"
        self.kafka_config["enable.auto.commit"] = "false"
        self.consumer = Consumer(self.kafka_config)
        self.topic = topic
        self.id = self.kafka_config["group.id"]
        self.subscribed = False
        self.open = False
        if self.config.schema_registry:
            self.schema_service = SchemaService(self.config)

    def __str__(self) -> str:
        return str(
            {
                "id": self.id,
                "topic": self.topic,
                "config": self.kafka_config,
                "subscribed": self.subscribed,
                "open": self.open,
            }
        )

    def consume(self, limit: int) -> List[Record]:
        if not self.subscribed:
            self.consumer.subscribe([self.topic.name])
            self.subscribed = True
            self.open = True

        records = []
        records_read = 0
        retries = 0

        while records_read < limit:
            if retries >= MAX_RETRIES_BEFORE_LEAVE:
                break

            raw_record = self.consumer.poll(CONSUMER_TIMEOUT)

            if raw_record is None or raw_record.error():
                retries += 1
                continue

            records_read += 1

            timestamp_available, timestamp = raw_record.timestamp()
            date = datetime.fromtimestamp(timestamp / 1000) if timestamp_available > 0 else None

            record = Record(
                date=date,
                partition=raw_record.partition(),
                offset=raw_record.offset(),
                headers=raw_record.headers(),
                key=raw_record.key(),
                value=raw_record.value(),
            )

            if self.config.schema_registry:
                self.__deserialize_key(raw_record, record)
                self.__deserialize_value(raw_record, record)

            records.append(record)

        return records

    def __deserialize_value(self, raw_record: Message, record: Record) -> None:
        if raw_record.value() is None:
            return

        value_schema_id = unpack_schema_id(raw_record.value())
        if value_schema_id <= 0:
            return

        schema = self.schema_service.get_schema(value_schema_id)
        record.value_schema = schema
        if schema is None:
            return

        if schema.type == AVRO:
            record.value = deserialize_avro(schema, raw_record.value())

    def __deserialize_key(self, raw_record: Message, record: Record) -> None:
        if raw_record.key() is None:
            return

        key_schema_id = unpack_schema_id(raw_record.key())
        if key_schema_id <= 0:
            return

        schema = self.schema_service.get_schema(key_schema_id)
        record.key_schema = schema
        if schema is None:
            return

        if schema.type == AVRO:
            record.key = deserialize_avro(schema, raw_record.key())

    def close(self) -> None:
        if self.config.schema_registry:
            self.schema_service.close()

        self.consumer.unsubscribe()
        self.subscribed = False
        self.consumer.close()
        self.open = False


if __name__ == "__main__":
    from rich import print

    from kaskade.renderables.kafka_record import KafkaRecord

    config = Config("kaskade.yml")
    topic = Topic(name="test")
    consumer_service = ConsumerService(config, topic)

    try:
        records = consumer_service.consume(1)
        print("consumer:", consumer_service.id)
        print("topic:", consumer_service.topic)
        print("total records:", len(records))
        record1 = records[0]
        kafka_record = KafkaRecord(record1, 150, 1)
        print(kafka_record)
    finally:
        consumer_service.close()
