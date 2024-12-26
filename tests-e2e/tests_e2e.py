import asyncio
import os


import unittest
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic
from parameterized import parameterized
from testcontainers.kafka import KafkaContainer, RedpandaContainer
from textual.widgets import DataTable
from textual.widgets._data_table import RowKey

from kaskade.admin import KaskadeAdmin
from kaskade.configs import BOOTSTRAP_SERVERS, EARLIEST, AUTO_OFFSET_RESET
from kaskade.consumer import KaskadeConsumer
from kaskade.deserializers import Deserialization
from kaskade.utils import load_properties

MY_VALUE = "my-value"
MY_KEY = "my-key"
MY_TOPIC = "my-topic"


CURRENT_PATH = os.getcwd()
PROPERTIES_PATH = (
    f"{CURRENT_PATH}/../.env" if CURRENT_PATH.endswith("tests-e2e") else f"{CURRENT_PATH}/.env"
)
SANDBOX_PROPERTIES = load_properties(PROPERTIES_PATH)
CONFLUENT_VERSION = SANDBOX_PROPERTIES["CONFLUENT_VERSION"]
REDPANDA_VERSION = SANDBOX_PROPERTIES["REDPANDA_VERSION"]
KAFKA_IMPLEMENTATIONS = [
    KafkaContainer(f"confluentinc/cp-kafka:{CONFLUENT_VERSION}").with_kraft(),
    RedpandaContainer(f"docker.redpanda.com/redpandadata/redpanda:{REDPANDA_VERSION}"),
]


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

    @parameterized.expand(KAFKA_IMPLEMENTATIONS)
    async def test_admin(self, kafka):
        with kafka:
            config = {BOOTSTRAP_SERVERS: kafka.get_bootstrap_server()}
            create_topic(config)

            admin_app = KaskadeAdmin(config)
            async with admin_app.run_test():
                await asyncio.sleep(10)
                table = admin_app.query_one(DataTable)
                self.assertEqual(1, len(table.rows))

                first_row = table._data[RowKey(MY_TOPIC)]
                first_column = list(first_row.values())[0]
                self.assertEqual(MY_TOPIC, first_column)

    @parameterized.expand(KAFKA_IMPLEMENTATIONS)
    async def test_consumer(self, kafka):
        with kafka:
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
                await asyncio.sleep(10)
                table = consumer_app.query_one(DataTable)
                self.assertEqual(1, len(table.rows))

                first_row = table._data[RowKey("0/0")]
                first_column = list(first_row.values())[0]
                second_column = list(first_row.values())[1]
                self.assertEqual(MY_KEY, first_column)
                self.assertEqual(MY_VALUE, second_column)


if __name__ == "__main__":
    unittest.main()
