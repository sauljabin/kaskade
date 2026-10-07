"""Unit test suite, isolated from the developer's Kaskade log and settings files."""

import atexit
import logging
import os
import tempfile
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from unittest.mock import patch

from kaskade import logger
from kaskade.settings import SETTINGS_ENV_VAR

_USER_FILES = tempfile.TemporaryDirectory(prefix="kaskade-unit-")
atexit.register(_USER_FILES.cleanup)
USER_FILES_DIRECTORY = Path(_USER_FILES.name)

# Importing any unit test module imports this package first, so the default log
# and settings paths resolve to the temporary directory for the whole run.
os.environ["XDG_CONFIG_HOME"] = str(USER_FILES_DIRECTORY / "config")
os.environ["XDG_STATE_HOME"] = str(USER_FILES_DIRECTORY / "state")
os.environ.pop(SETTINGS_ENV_VAR, None)


def close_log_handlers_on_cleanup(test: unittest.TestCase) -> None:
    """Close file handlers that ``configure_logging`` attaches during the test.

    ``assertLogs`` restores the previous handlers on exit and drops any handler
    attached meanwhile without closing it, so handlers are tracked at creation.
    """
    handlers: list[logging.Handler] = []
    level, propagate = logger.level, logger.propagate

    def create_handler(*args: Any, **kwargs: Any) -> RotatingFileHandler:
        handler = RotatingFileHandler(*args, **kwargs)
        handlers.append(handler)
        return handler

    def close_handlers() -> None:
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        logger.setLevel(level)
        logger.propagate = propagate

    patcher = patch("kaskade.logs.RotatingFileHandler", side_effect=create_handler)
    patcher.start()
    test.addCleanup(close_handlers)
    test.addCleanup(patcher.stop)
