import logging
from pathlib import Path

from kaskade import APP_LOG, logger

LOG_FORMAT = "%(asctime)-15s %(levelname)-8s %(message)s"


def configure_logging(path: Path | None = None) -> bool:
    """Configure Kaskade's file logger without making startup fragile."""
    if any(getattr(handler, "_kaskade_handler", False) for handler in logger.handlers):
        return True

    log_path = Path(APP_LOG) if path is None else path
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path)
    except OSError:
        return False

    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler._kaskade_handler = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return True
