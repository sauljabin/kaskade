import asyncio
import configparser
import struct
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar

from confluent_kafka import KafkaException
from fastavro import schemaless_writer
from fastavro.schema import load_schema
from textual.app import App

from kaskade import logger

T = TypeVar("T")


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


async def run_blocking(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run a blocking call in a worker thread without blocking the event loop.

    A thread cannot be interrupted, so cancelling the caller waits for the call to
    finish before re-raising ``CancelledError``: locks the caller holds stay held,
    and a client it closes next is never still in use. The cancellation wins over
    the call's own outcome; a failure is logged instead of raised. Cancelling the
    caller again while it waits stops the wait, not the call.
    """
    call = asyncio.ensure_future(asyncio.to_thread(func, *args, **kwargs))
    try:
        return await asyncio.shield(call)
    except asyncio.CancelledError:
        await asyncio.wait({call})
        if not call.cancelled() and (error := call.exception()) is not None:
            logger.warning("blocking call failed after its caller was cancelled: %r", error)
        raise


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
