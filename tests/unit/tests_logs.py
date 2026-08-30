import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kaskade import logger
from kaskade.logs import configure_logging


class TestLogging(unittest.TestCase):
    def setUp(self) -> None:
        self.configured_handlers = [
            handler for handler in logger.handlers if getattr(handler, "_kaskade_handler", False)
        ]
        for handler in self.configured_handlers:
            logger.removeHandler(handler)

    def tearDown(self) -> None:
        for handler in list(logger.handlers):
            if getattr(handler, "_kaskade_handler", False):
                logger.removeHandler(handler)
                handler.close()
        for handler in self.configured_handlers:
            logger.addHandler(handler)

    def test_configures_named_file_logger_lazily_and_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "nested" / "kaskade.log"

            self.assertTrue(configure_logging(log_path))
            self.assertTrue(configure_logging(log_path))

            configured = [
                handler
                for handler in logger.handlers
                if getattr(handler, "_kaskade_handler", False)
            ]
            self.assertEqual("kaskade", logger.name)
            self.assertEqual(1, len(configured))
            self.assertTrue(log_path.exists())

    def test_logging_failure_does_not_break_startup(self) -> None:
        with patch("kaskade.logs.logging.FileHandler", side_effect=OSError("read only")):
            self.assertFalse(configure_logging(Path("/unavailable/kaskade.log")))

        self.assertFalse(
            any(getattr(handler, "_kaskade_handler", False) for handler in logger.handlers)
        )


if __name__ == "__main__":
    unittest.main()
