import re

reg_expression = re.compile("^[a-zA-Z0-9._-]+$")


def validate_topic_name(name: str) -> bool:
    return bool(reg_expression.match(name))
