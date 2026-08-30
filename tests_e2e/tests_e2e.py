import asyncio
import os
import unittest

from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic
from testcontainers.kafka import KafkaContainer
from textual.widgets import DataTable

from kaskade.admin import KaskadeAdmin
from kaskade.configs import AUTO_OFFSET_RESET, BOOTSTRAP_SERVERS, EARLIEST
from kaskade.consumer import KaskadeConsumer
from kaskade.deserializers import Deserialization
from kaskade.utils import load_properties

MY_VALUE = "my-value"
MY_KEY = "my-key"
MY_TOPIC = "my-topic"


CURRENT_PATH = os.getcwd()
PROPERTIES_PATH = (
    f"{CURRENT_PATH}/../.env" if CURRENT_PATH.endswith("tests_e2e") else f"{CURRENT_PATH}/.env"
)
SANDBOX_PROPERTIES = load_properties(PROPERTIES_PATH)
CONFLUENT_VERSION = SANDBOX_PROPERTIES["CONFLUENT_VERSION"]


def kafka_container() -> KafkaContainer:
    return KafkaContainer(f"confluentinc/cp-kafka:{CONFLUENT_VERSION}").with_kraft()


def create_topic(config):
    admin_client = AdminClient(config)
    futures = admin_client.create_topics([NewTopic(MY_TOPIC)]).values()
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


if __name__ == "__main__":
    unittest.main()
