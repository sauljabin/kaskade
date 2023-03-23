import logging
from pathlib import Path

from importlib.metadata import version

APP_NAME = "kaskade"


def get_kaskade_home() -> Path:
    path_home = Path.home()
    kaskade_path = path_home.joinpath("." + APP_NAME)
    if not kaskade_path.exists():
        kaskade_path.mkdir()
    return kaskade_path


__version__ = APP_VERSION = version(APP_NAME)
APP_HOME = str(get_kaskade_home())
APP_LOG = str(get_kaskade_home().joinpath(APP_NAME + ".log"))

logger_handler = logging.FileHandler(APP_LOG)
logger_handler.setFormatter(
    logging.Formatter("%(asctime)-15s %(levelname)-8s %(message)s")
)

logger = logging.getLogger()
logger.addHandler(logger_handler)
logger.setLevel(logging.INFO)

APP_DOC = "https://github.com/sauljabin/kaskade"
APP_LICENSE = "MIT"
