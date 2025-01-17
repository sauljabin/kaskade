import asyncio
import functools
import struct
from io import BytesIO
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Any

from confluent_kafka import KafkaException
from fastavro import schemaless_writer
from fastavro.schema import load_schema
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


def pack_bytes(struct_format: str, data: Any) -> bytes:
    return struct.pack(struct_format, data)


def file_to_bytes(file_path: str) -> bytes:
    path = Path(file_path).expanduser()
    return path.read_bytes()


def file_to_str(file_path: str) -> str:
    path = Path(file_path).expanduser()
    return path.read_text()


def load_properties(file_path: str, sep: str = "=", comment_char: str = "#") -> dict[str, str]:
    props = {}
    lines = file_to_str(file_path).split("\n")

    for line in lines:
        line = line.strip()
        if line and not line.startswith(comment_char) and sep in line:
            key_value = line.split(sep, maxsplit=1)
            key = key_value[0].strip()
            value = key_value[1].strip().strip('"')
            props[key] = value

    return props


def py_to_avro(schema_path: str, data: dict[str, Any] | MappingProxyType[str, Any]) -> bytes:
    schema = load_schema(schema_path)
    buffer_writer = BytesIO()
    schemaless_writer(buffer_writer, schema, data)
    return buffer_writer.getvalue()
