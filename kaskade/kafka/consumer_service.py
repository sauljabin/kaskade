import uuid
from datetime import datetime
from typing import List

from confluent_kafka import Consumer

from kaskade.config import Config
from kaskade.kafka.models import Record, Topic

CONSUMER_TIMEOUT = 0.5

MAX_RETRIES_BEFORE_LEAVE = 10


class ConsumerService:
    def __init__(self, config: Config, topic: Topic) -> None:
        if config is None or config.kafka is None:
            raise Exception("Config not found")
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

            msg = self.consumer.poll(CONSUMER_TIMEOUT)

            if msg is None or msg.error():
                retries += 1
                continue

            records_read += 1

            timestamp_available, timestamp = msg.timestamp()
            date = (
                datetime.fromtimestamp(timestamp / 1000)
                if timestamp_available > 0
                else None
            )
            record = Record(
                date=date,
                partition=msg.partition(),
                offset=msg.offset(),
                headers=msg.headers(),
                key=msg.key(),
                value=msg.value(),
            )
            records.append(record)

        return records

    def close(self) -> None:
        self.consumer.unsubscribe()
        self.subscribed = False
        self.consumer.close()
        self.open = False


if __name__ == "__main__":
    from pprint import pprint

    config = Config("../../kaskade.yml")
    topic = Topic(name="kafka-cluster.test")
    consumer_service = ConsumerService(config, topic)

    try:
        records = consumer_service.consume(100)
        print("consumer:", consumer_service.id)
        print("topic:", consumer_service.topic)
        print("total records:", len(records))
        pprint(records)
    finally:
        consumer_service.close()
