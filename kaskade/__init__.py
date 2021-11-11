import logging
from pathlib import Path

import pkg_resources

APP_NAME = "kaskade"


def get_kaskade_home() -> Path:
    path_home = Path.home()
    kaskade_path = path_home.joinpath("." + APP_NAME)
    if not kaskade_path.exists():
        kaskade_path.mkdir()
    return kaskade_path


__version__ = APP_VERSION = pkg_resources.get_distribution(APP_NAME).version
APP_HOME = str(get_kaskade_home())
APP_LOG = str(get_kaskade_home().joinpath(APP_NAME + ".log"))

logger = logging.getLogger()
logger.addHandler(logging.FileHandler(APP_LOG))
logger.setLevel(logging.DEBUG)
