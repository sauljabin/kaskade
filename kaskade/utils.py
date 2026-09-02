import asyncio
import configparser
import functools
import struct
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from types import MappingProxyType
from typing import Any

from confluent_kafka import KafkaException
from fastavro import schemaless_reader, schemaless_writer
from fastavro.schema import load_schema
from textual.app import App

from kaskade import logger


class _CaseSensitiveConfigParser(configparser.ConfigParser):
    def optionxform(self, optionstr: str) -> str:
        return optionstr


def copy_text(application: App, text: str, subject: str) -> None:
    """Copy text through Textual and confirm the contextual result."""
    application.copy_to_clipboard(text)
    application.notify(f"Copied {subject} to clipboard", title="Copied")


def notify_error(application: App, title: str, ex: Exception) -> None:
    message = str(ex)

    if isinstance(ex, KafkaException) and len(ex.args) > 0 and hasattr(ex.args[0], "str"):
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


def load_ini(file_path: str) -> dict[str, dict[str, str]]:
    parser = _CaseSensitiveConfigParser(interpolation=None, delimiters=("=",))

    try:
        parser.read_string(file_to_str(file_path))
    except configparser.Error as ex:
        raise ValueError(f"Invalid INI: {ex}") from ex

    return {section: dict(parser.items(section, raw=True)) for section in parser.sections()}


def py_to_avro(schema_path: str, data: dict[str, Any] | MappingProxyType[str, Any]) -> bytes:
    schema = load_schema(schema_path)
    buffer = BytesIO()
    schemaless_writer(buffer, schema, data)
    return buffer.getvalue()


def avro_to_py(schema_path: str, data: bytes) -> Any:
    schema = load_schema(schema_path)
    buffer = BytesIO(data)
    return schemaless_reader(buffer, schema, None)
