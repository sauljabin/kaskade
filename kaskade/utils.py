import asyncio
import functools
import struct
from pathlib import Path
from typing import Callable, Any

from confluent_kafka import KafkaException
from textual.app import App

from kaskade import logger


def notify_error(application: App, title: str, ex: Exception) -> None:
    message = str(ex)

    if isinstance(ex, KafkaException):
        if len(ex.args) > 0 and hasattr(ex.args[0], "str"):
            message = ex.args[0].str()

    logger.exception(ex)
    application.notify(message, severity="error", title=title)


async def make_it_async(func: Callable[..., Any], /, *args: Any, **keywords: Any) -> Any:
    return await asyncio.get_running_loop().run_in_executor(
        None, functools.partial(func, *args, **keywords)
    )


def unpack_bytes(struct_format: str, data: bytes) -> Any:
    return struct.unpack(struct_format, data)[0]


def file_to_bytes(str_path: str) -> bytes:
    path = Path(str_path).expanduser()
    return path.read_bytes()
