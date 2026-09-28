from confluent_kafka import KafkaException
from textual.app import App

from kaskade import logger


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
