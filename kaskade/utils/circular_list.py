from typing import Generic, List, Optional, TypeVar

T = TypeVar("T")


class CircularList(Generic[T]):
    def __init__(self, wrapped: List[T]) -> None:
        self.list = wrapped
        self.index = -1

    @property
    def current(self) -> Optional[T]:
        if self.index < 0 or self.index >= len(self.list):
            return None

        return self.list[self.index]

    @current.setter
    def current(self, current: Optional[T]) -> None:
        if current is None:
            self.reset()
            return

        if current in self.list:
            self.index = self.list.index(current)
        else:
            self.reset()

    def reset(self) -> None:
        self.index = -1

    def __next__(self) -> T:
        return self.next()

    def __len__(self) -> int:
        return len(self.list)

    def next(self) -> T:
        self.index += 1
        if self.index >= len(self.list):
            self.index = 0
        return self.list[self.index]

    def previous(self) -> T:
        self.index -= 1
        if self.index < 0:
            self.index = len(self.list) - 1
        return self.list[self.index]
