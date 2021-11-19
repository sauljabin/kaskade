from typing import Generic, List, Optional, TypeVar

from rich.text import Text

from kaskade.unicodes import RIGHT_TRIANGLE

T = TypeVar("T")


class ScrollableList(Generic[T]):
    __pointer: int = -1

    def __init__(
        self,
        wrapped: List[T],
        max_len: int = -1,
        pointer: int = -1,
        selected: Optional[T] = None,
    ) -> None:
        self.list = wrapped if wrapped else []
        self.max_len = (
            len(self.list) if max_len < 0 or max_len > len(self.list) else max_len
        )
        self.start_rendering = 0
        self.end_rendering = self.max_len
        if 0 <= pointer < len(self.list):
            self.pointer = pointer

        if selected is not None:
            self.selected = selected

    def __rich__(self) -> Text:
        content = Text(overflow="ellipsis", no_wrap=True)
        for index in range(self.start_rendering, self.end_rendering):
            item = self.list[index]
            string_index = str(index + 1)
            string_item = str(item)
            if self.selected == item:
                content.append(RIGHT_TRIANGLE, "green bold")
                content.append(" ")
                content.append(string_index, "bright_magenta bold")
                content.append(" ")
                content.append(string_item, "green bold")
            else:
                content.append("  ")
                content.append(string_index, "bright_magenta")
                content.append(" ")
                content.append(string_item)
            content.append("\n")
        return content

    @property
    def selected(self) -> Optional[T]:
        if self.pointer < 0 or self.pointer >= len(self.list):
            return None

        return self.list[self.pointer]

    @selected.setter
    def selected(self, selected: Optional[T]) -> None:
        if selected is None:
            self.reset()
            return

        if selected in self.list:
            self.pointer = self.list.index(selected)
        else:
            self.reset()

    def __str__(self) -> str:
        return str(self.renderables())

    def renderables(self) -> List[T]:
        return self.list[self.start_rendering : self.end_rendering]

    def reset(self) -> None:
        self.__pointer = -1
        self.start_rendering = 0
        self.end_rendering = self.max_len

    @property
    def pointer(self) -> int:
        return self.__pointer

    @pointer.setter
    def pointer(self, pointer: int) -> None:
        if pointer < 0:
            self.__pointer = len(self.list) - 1
            self.end_rendering = len(self.list)
            self.start_rendering = self.end_rendering - self.max_len
        elif pointer >= len(self.list):
            self.__pointer = 0
            self.start_rendering = 0
            self.end_rendering = self.max_len
        elif pointer < self.start_rendering:
            self.__pointer = pointer
            self.start_rendering = pointer
            self.end_rendering = pointer + self.max_len
        elif pointer >= self.end_rendering:
            self.__pointer = pointer
            self.start_rendering = pointer - self.max_len + 1
            self.end_rendering = pointer + 1
        else:
            self.__pointer = pointer

    def previous(self) -> None:
        self.pointer -= 1

    def next(self) -> None:
        self.pointer += 1
