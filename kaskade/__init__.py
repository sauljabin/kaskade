import logging
from importlib.metadata import version
from pathlib import Path

APP_NAME = "kaskade"
__version__ = APP_VERSION = version(APP_NAME)
APP_BANNER = r""" _             _             _
| | ____ _ ___| | ____ _  __| | ___
| |/ / _` / __| |/ / _` |/ _` |/ _ \
|   < (_| \__ \   < (_| | (_| |  __/
|_|\_\__,_|___/_|\_\__,_|\__,_|\___|"""

APP_HOME = str(Path.home() / f".{APP_NAME}")
APP_LOG = str(Path(APP_HOME) / f"{APP_NAME}.log")

logger = logging.getLogger(APP_NAME)
logger.addHandler(logging.NullHandler())
