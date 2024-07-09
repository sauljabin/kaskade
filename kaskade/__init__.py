import logging
from importlib.metadata import version
from pathlib import Path

APP_NAME = "kaskade"
APP_NAME_SHORT = "kskd"
__version__ = APP_VERSION = version(APP_NAME)
APP_BANNER = r""" _             _             _
| | ____ _ ___| | ____ _  __| | ___
| |/ / _` / __| |/ / _` |/ _` |/ _ \
|   < (_| \__ \   < (_| | (_| |  __/
|_|\_\__,_|___/_|\_\__,_|\__,_|\___|"""
APP_BANNER_SHORT = r""" _        _       _
| | _____| | ____| |
| |/ / __| |/ / _` |
|   <\__ \   < (_| |
|_|\_\___/_|\_\__,_|"""


def get_kaskade_home() -> Path:
    path_home = Path.home()
    kaskade_path = path_home.joinpath("." + APP_NAME)
    if not kaskade_path.exists():
        kaskade_path.mkdir()
    return kaskade_path


APP_HOME = str(get_kaskade_home())
APP_LOG = str(get_kaskade_home().joinpath(APP_NAME + ".log"))

logger_handler = logging.FileHandler(APP_LOG)
logger_handler.setFormatter(logging.Formatter("%(asctime)-15s %(levelname)-8s %(message)s"))

logger = logging.getLogger()
logger.addHandler(logger_handler)
logger.setLevel(logging.INFO)
