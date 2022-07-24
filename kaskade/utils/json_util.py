import json
from typing import Any


def json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=4).strip()
