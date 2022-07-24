from typing import Any


def decode_if_byte(value: Any) -> Any:
    return value.decode("utf-8") if type(value) is bytes else value
