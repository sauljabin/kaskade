import asyncio
import unittest

from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic
from testcontainers.community.kafka import KafkaContainer
from textual.widgets import DataTable

from kaskade.admin import KaskadeAdmin
from kaskade.configs import AUTO_OFFSET_RESET, BOOTSTRAP_SERVERS, EARLIEST
from kaskade.consumer import KaskadeConsumer
from kaskade.deserializers import Deserialization
from kaskade.models import PartitionOffset, PartitionSelection

MY_VALUE = "my-value"
MY_KEY = "my-key"
MY_TOPIC = "my-topic"


KAFKA_IMAGE = "confluentinc/cp-kafka:8.1.0"


def kafka_container() -> KafkaContainer:
    return KafkaContainer(KAFKA_IMAGE).with_kraft()


def create_topic(config, partitions: int = 1):
    admin_client = AdminClient(config)
    futures = admin_client.create_topics(
        [NewTopic(MY_TOPIC, num_partitions=partitions, replication_factor=1)]
    ).values()
    for future in futures:
        future.result()


def populate_topic(config):
    producer = Producer(config)
    producer.produce(MY_TOPIC, key=MY_KEY, value=MY_VALUE)
    producer.flush()


class TestE2E(unittest.IsolatedAsyncioTestCase):
    async def wait_for_rows(self, table: DataTable, expected: int, timeout: float = 15) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while len(table.rows) != expected:
            if loop.time() >= deadline:
                self.fail(f"Expected {expected} row(s), found {len(table.rows)}")
            await asyncio.sleep(0.1)

    async def test_admin(self):
        with kafka_container() as kafka:
            config = {BOOTSTRAP_SERVERS: kafka.get_bootstrap_server()}
            create_topic(config)

            admin_app = KaskadeAdmin(config)
            async with admin_app.run_test():
                table = admin_app.query_one(DataTable)
                await self.wait_for_rows(table, 1)

                self.assertEqual(MY_TOPIC, table.get_row(MY_TOPIC)[0])

    async def test_consumer(self):
        with kafka_container() as kafka:
            config = {BOOTSTRAP_SERVERS: kafka.get_bootstrap_server()}
            create_topic(config)
            populate_topic(config)

            consumer_app = KaskadeConsumer(
                MY_TOPIC,
                config | {AUTO_OFFSET_RESET: EARLIEST},
                {},
                {},
                {},
                Deserialization.STRING,
                Deserialization.STRING,
            )
            async with consumer_app.run_test():
                table = consumer_app.query_one(DataTable)
                await self.wait_for_rows(table, 1)

                first_row = table.get_row("0/0")
                self.assertEqual(MY_KEY, first_row[0])
                self.assertEqual(MY_VALUE, first_row[1])

    async def test_consumer_assigns_only_explicit_partition(self):
        with kafka_container() as kafka:
            config = {BOOTSTRAP_SERVERS: kafka.get_bootstrap_server()}
            create_topic(config, partitions=2)
            producer = Producer(config)
            producer.produce(MY_TOPIC, key="ignored", value="partition-0", partition=0)
            producer.produce(MY_TOPIC, key="selected", value="partition-1", partition=1)
            producer.flush()

            consumer_app = KaskadeConsumer(
                MY_TOPIC,
                config,
                {},
                {},
                {},
                Deserialization.STRING,
                Deserialization.STRING,
                partitions=(PartitionSelection(1, PartitionOffset.EARLIEST),),
            )
            async with consumer_app.run_test():
                table = consumer_app.query_one(DataTable)
                await self.wait_for_rows(table, 1)

                selected_row = table.get_row("1/0")
                self.assertEqual("selected", selected_row[0])
                self.assertEqual("partition-1", selected_row[1])


if __name__ == "__main__":
    unittest.main()
