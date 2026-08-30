import json
from datetime import datetime, timezone
from io import StringIO

from rich.json import JSON
from textual.app import App

from kaskade.models import Record


def record_json(record: Record) -> str:
    """Return a readable JSON representation of a consumed record."""
    return json.dumps(record.dict(), indent=2, ensure_ascii=False, default=str) + "\n"


def record_json_renderable(data: object) -> JSON:
    """Return syntax-highlighted, indented JSON that wraps long values."""
    renderable = JSON.from_data(data, indent=2, ensure_ascii=False, default=str)
    renderable.text.no_wrap = False
    renderable.text.overflow = "fold"
    return renderable


def record_filename(record: Record, exported_at: datetime | None = None) -> str:
    """Build a screenshot-style, collision-resistant record export filename."""
    export_time = exported_at or datetime.now(timezone.utc).astimezone()
    timestamp = export_time.replace(tzinfo=None).isoformat()
    filename_stem = f"kaskade-record-{record.topic}-{record.partition}-{record.offset}_{timestamp}"
    for reserved_character in ' <>:"/\\|?*.':
        filename_stem = filename_stem.replace(reserved_character, "_")
    return f"{filename_stem}.json"


def deliver_record(application: App[object], record: Record) -> None:
    """Deliver a record to the same destination used by Textual screenshots."""
    application.deliver_text(
        StringIO(record_json(record)),
        save_filename=record_filename(record),
        encoding="utf-8",
        mime_type="application/json",
        name="record",
    )
