import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kaskade import logger
from kaskade.logs import (
    LOG_BACKUP_COUNT,
    LOG_MAX_BYTES,
    RotatingFileHandler,
    configure_logging,
    default_log_path,
)


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
            self.assertIsInstance(configured[0], RotatingFileHandler)
            self.assertEqual(LOG_MAX_BYTES, configured[0].maxBytes)
            self.assertEqual(LOG_BACKUP_COUNT, configured[0].backupCount)
            self.assertEqual("utf-8", configured[0].encoding.lower())

    def test_default_log_path_uses_xdg_state_home(self) -> None:
        path = default_log_path(
            environ={"XDG_STATE_HOME": "/tmp/xdg-state"},
            home=Path("/users/kaskade"),
        )

        self.assertEqual(Path("/tmp/xdg-state/kaskade/kaskade.log"), path)

    def test_default_log_path_uses_home_fallback(self) -> None:
        path = default_log_path(environ={}, home=Path("/users/kaskade"))

        self.assertEqual(Path("/users/kaskade/.local/state/kaskade/kaskade.log"), path)

    def test_rotates_log_files_at_the_size_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch("kaskade.logs.LOG_MAX_BYTES", 100):
            log_path = Path(directory) / "kaskade.log"
            self.assertTrue(configure_logging(log_path))

            logger.info("x" * 100)
            logger.info("next record")
            for handler in logger.handlers:
                handler.flush()

            self.assertTrue(log_path.exists())
            self.assertTrue(Path(f"{log_path}.1").exists())

    def test_logging_failure_does_not_break_startup(self) -> None:
        with patch("kaskade.logs.RotatingFileHandler", side_effect=OSError("read only")):
            self.assertFalse(configure_logging(Path("/unavailable/kaskade.log")))

        self.assertFalse(
            any(getattr(handler, "_kaskade_handler", False) for handler in logger.handlers)
        )


if __name__ == "__main__":
    unittest.main()
