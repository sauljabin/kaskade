import asyncio
import os

from io import StringIO
import rich

import unittest
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic
from parameterized import parameterized
from testcontainers.kafka import KafkaContainer
from textual.widgets import DataTable
from textual.widgets._data_table import RowKey

from kaskade.admin import KaskadeAdmin
from kaskade.configs import BOOTSTRAP_SERVERS, EARLIEST, AUTO_OFFSET_RESET
from kaskade.consumer import KaskadeConsumer
from kaskade.deserializers import Format
from kaskade.utils import load_properties


MY_TOPIC = "my-topic"


CURRENT_PATH = os.getcwd()
PROPERTIES_PATH = (
    f"{CURRENT_PATH}/../.env" if CURRENT_PATH.endswith("tests-e2e") else f"{CURRENT_PATH}/.env"
)
SANDBOX_PROPERTIES = load_properties(PROPERTIES_PATH)
CP_VERSION = SANDBOX_PROPERTIES["CP_VERSION"]
RP_VERSION = SANDBOX_PROPERTIES["RP_VERSION"]
KAFKA_IMPLEMENTATIONS = [
    KafkaContainer(f"confluentinc/cp-kafka:{CP_VERSION}").with_kraft(),
    # waiting for https://github.com/confluentinc/confluent-kafka-python/issues/1842
    # RedpandaContainer(f"docker.redpanda.com/redpandadata/redpanda:{RP_VERSION}"),
]


def create_topic(config):
    admin_client = AdminClient(config)
    futures = admin_client.create_topics([NewTopic(MY_TOPIC)]).values()
    for future in futures:
        future.result()


def populate_topic(config):
    producer = Producer(config)
    producer.produce(MY_TOPIC, key="my-key", value="my-value")
    producer.flush()


class TestE2E(unittest.IsolatedAsyncioTestCase):

    @parameterized.expand(KAFKA_IMPLEMENTATIONS)
    async def test_admin(self, kafka):
        with kafka:
            config = {BOOTSTRAP_SERVERS: kafka.get_bootstrap_server()}
            create_topic(config)

            admin_app = KaskadeAdmin(config)
            async with admin_app.run_test():
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
                Format.STRING,
                Format.STRING,
            )
            async with consumer_app.run_test():
                await asyncio.sleep(10)
                table = consumer_app.query_one(DataTable)
                self.assertEqual(1, len(table.rows))

                record_id = "0/0"
                first_row = table._data[RowKey(record_id)]
                first_column = list(first_row.values())[0]
                string_out = StringIO()
                rich.print(first_column, file=string_out)
                self.assertIn("my-key", string_out.getvalue())
                self.assertIn("my-value", string_out.getvalue())


if __name__ == "__main__":
    unittest.main()
