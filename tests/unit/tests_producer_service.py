import asyncio
import threading
import unittest
from unittest.mock import MagicMock, patch

from confluent_kafka import TIMESTAMP_CREATE_TIME, KafkaError

from kaskade import logger
from kaskade.producer_service import (
    Delivery,
    DeliveryError,
    DeliveryFailure,
    DeliveryInProgressError,
    OutgoingRecord,
    ProducerService,
    ProducerSettings,
)
from kaskade.timeouts import TimeoutConfig

RECORD = OutgoingRecord(key=b"", value=None, headers=(("a", "1"), ("a", None)), partition=2)


def acknowledged(partition: int = 2, offset: int = 41) -> MagicMock:
    message = MagicMock()
    message.partition.return_value = partition
    message.offset.return_value = offset
    message.timestamp.return_value = (TIMESTAMP_CREATE_TIME, 1_700_000_000_120)
    return message


class TestProducerService(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        patcher = patch("kaskade.producer_service.Producer")
        self.addCleanup(patcher.stop)
        self.producer_class = patcher.start()
        self.producer = self.producer_class.return_value
        self.settings = ProducerSettings(
            "orders",
            {"bootstrap.servers": "kafka:9092"},
            timeouts=TimeoutConfig(producer_delivery=0.3, producer_flush=0.2),
        )
        self.service = ProducerService(self.settings)

    def deliver_on_poll(self, error: KafkaError | None, message: object) -> None:
        def poll(_: float) -> int:
            on_delivery = self.producer.produce.call_args.kwargs["on_delivery"]
            on_delivery(error, message)
            return 1

        self.producer.poll.side_effect = poll

    def test_construction_performs_no_io(self):
        self.producer_class.assert_not_called()
        self.service.start()
        self.producer_class.assert_called_once_with(
            {"bootstrap.servers": "kafka:9092"}, logger=logger
        )

    async def test_reports_success_only_after_the_delivery_callback(self):
        self.deliver_on_poll(None, acknowledged())

        delivery = await self.service.produce(RECORD)

        self.producer.produce.assert_called_once()
        call = self.producer.produce.call_args
        self.assertEqual(("orders",), call.args)
        self.assertEqual(b"", call.kwargs["key"])
        self.assertIsNone(call.kwargs["value"])
        self.assertEqual([("a", "1"), ("a", None)], call.kwargs["headers"])
        self.assertEqual(2, call.kwargs["partition"])
        self.assertEqual((2, 41), (delivery.partition, delivery.offset))
        self.assertIn("Delivered · Partition 2 · Offset 41 · ", delivery.summary())

    async def test_automatic_partition_omits_the_partition(self):
        self.deliver_on_poll(None, acknowledged())

        await self.service.produce(OutgoingRecord(key=None, value=b"v"))

        self.assertNotIn("partition", self.producer.produce.call_args.kwargs)

    async def test_classifies_delivery_failures(self):
        cases = (
            (KafkaError.TOPIC_AUTHORIZATION_FAILED, DeliveryFailure.AUTHORIZATION),
            (KafkaError._MSG_TIMED_OUT, DeliveryFailure.TIMEOUT),
            (KafkaError._UNKNOWN_PARTITION, DeliveryFailure.BROKER),
        )
        for code, failure in cases:
            with self.subTest(code=code):
                self.deliver_on_poll(KafkaError(code), acknowledged())
                with self.assertRaises(DeliveryError) as raised:
                    await self.service.produce(RECORD)
                self.assertEqual(failure, raised.exception.failure)
                self.assertFalse(self.service.is_delivering)

    async def test_times_out_without_an_acknowledgement(self):
        self.producer.poll.return_value = 0

        with self.assertRaises(DeliveryError) as raised:
            await self.service.produce(RECORD)

        self.assertEqual(DeliveryFailure.TIMEOUT, raised.exception.failure)
        self.assertIn("may still be delivered", str(raised.exception))

    async def test_rejects_a_second_delivery_in_progress(self):
        polling = threading.Event()
        release = threading.Event()

        def poll(_: float) -> int:
            polling.set()
            release.wait(1)
            on_delivery = self.producer.produce.call_args.kwargs["on_delivery"]
            on_delivery(None, acknowledged())
            return 1

        self.producer.poll.side_effect = poll
        first = asyncio.create_task(self.service.produce(RECORD))
        await asyncio.to_thread(polling.wait, 1)

        self.assertTrue(self.service.is_delivering)
        with self.assertRaises(DeliveryInProgressError):
            await self.service.produce(RECORD)
        release.set()
        self.assertIsInstance(await first, Delivery)
        self.assertEqual(1, self.producer.produce.call_count)

    async def test_close_flushes_within_the_flush_deadline(self):
        self.service.start()
        self.producer.flush.return_value = 1

        with self.assertLogs("kaskade", level="WARNING") as logs:
            await self.service.aclose()

        self.producer.flush.assert_called_once_with(0.2)
        self.assertIn("1 record(s) were not delivered", logs.output[0])

    async def test_closing_interrupts_a_pending_delivery(self):
        self.producer.poll.side_effect = lambda _: self.service._closing.set() or 0

        with self.assertRaisesRegex(DeliveryError, "closed before the broker acknowledged"):
            await self.service.produce(RECORD)


if __name__ == "__main__":
    unittest.main()
