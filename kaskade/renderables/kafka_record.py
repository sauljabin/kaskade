from rich.syntax import Syntax

from kaskade.kafka.models import Record


class KafkaRecord:
    def __init__(self, record: Record, page_size: int, line: int) -> None:
        self.record = record
        self.record_json = self.record.json().strip()
        self.page_size = page_size
        self.line = line

    def __str__(self) -> str:
        return self.record.json()

    def __rich__(self) -> Syntax:
        initial_position = self.line - 1
        final_position = self.line - 1 + self.page_size

        lines = self.record_json.split("\n")
        to_render = "\n".join(lines[initial_position:final_position])

        return Syntax(
            to_render,
            "json",
            word_wrap=True,
            padding=(0, 1, 0, 1),
            theme="ansi_dark",
            background_color="default",
        )
