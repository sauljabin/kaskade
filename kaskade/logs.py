import logging
import os
from collections.abc import Mapping
from logging.handlers import RotatingFileHandler
from pathlib import Path

from kaskade import APP_NAME, logger

LOG_FORMAT = "%(asctime)-15s %(levelname)-8s %(message)s"
LOG_FILE_NAME = f"{APP_NAME}.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3


def default_log_path(environ: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    """Return Kaskade's XDG state log path on Linux and macOS."""
    environment = os.environ if environ is None else environ
    home_path = Path.home() if home is None else home
    state_home = environment.get("XDG_STATE_HOME")
    base_path = Path(state_home).expanduser() if state_home else home_path / ".local" / "state"
    return base_path / APP_NAME / LOG_FILE_NAME


def configure_logging(path: Path | None = None) -> bool:
    """Configure Kaskade's file logger without making startup fragile."""
    if any(getattr(handler, "_kaskade_handler", False) for handler in logger.handlers):
        return True

    log_path = default_log_path() if path is None else path
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        return False

    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler._kaskade_handler = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return True
