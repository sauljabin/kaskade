import asyncio
import threading
import unittest

from kaskade import logger
from kaskade.concurrency import run_blocking


class TestRunBlocking(unittest.IsolatedAsyncioTestCase):
    async def test_returns_the_result_of_the_call(self) -> None:
        self.assertEqual(3, await run_blocking(sum, [1, 2]))

    async def test_raises_the_failure_of_the_call(self) -> None:
        with self.assertRaises(ValueError):
            await run_blocking(int, "not a number")

    async def test_cancellation_waits_for_the_call_and_logs_its_failure(self) -> None:
        started = threading.Event()
        release = threading.Event()

        def fail_when_released() -> None:
            started.set()
            release.wait(timeout=2)
            raise ValueError("broker went away")

        task = asyncio.create_task(run_blocking(fail_when_released))
        await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0.05)
        self.assertFalse(task.done())

        release.set()
        with self.assertLogs(logger, "WARNING") as logs, self.assertRaises(asyncio.CancelledError):
            await task

        self.assertIn("broker went away", logs.output[0])


if __name__ == "__main__":
    unittest.main()
