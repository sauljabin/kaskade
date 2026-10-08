from confluent_kafka import KafkaException
from textual.app import App

from kaskade import logger


def copy_text(application: App, text: str, subject: str) -> None:
    """Copy text through Textual and confirm the contextual result."""
    application.copy_to_clipboard(text)
    application.notify(f"Copied {subject} to clipboard", title="Copied")


def error_message(ex: Exception) -> str:
    """Return a readable message, using the Kafka error text instead of its repr."""
    if isinstance(ex, KafkaException) and len(ex.args) > 0 and hasattr(ex.args[0], "str"):
        return str(ex.args[0].str())
    return str(ex)


def notify_error(application: App, title: str, ex: Exception) -> None:
    logger.exception(ex)
    application.notify(error_message(ex), severity="error", title=title)
