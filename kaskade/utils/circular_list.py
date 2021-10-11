from typing import Any, List


class CircularList:
    def __init__(self, wrapped: List[Any]) -> None:
        self.list = wrapped
        self.index = -1

    def reset(self) -> None:
        self.index = -1

    def __next__(self) -> Any:
        return self.next()

    def __len__(self) -> int:
        return len(self.list)

    def next(self) -> Any:
        self.index += 1
        if self.index >= len(self.list):
            self.index = 0
        return self.list[self.index]

    def previous(self) -> Any:
        self.index -= 1
        if self.index < 0:
            self.index = len(self.list) - 1
        return self.list[self.index]
