from typing import List, TypeVar

from rich.text import Text

from kaskade.unicodes import RIGHT_TRIANGLE

T = TypeVar("T")


class ScrollableList:
    def __init__(self, wrapped: List[T], max_len: int = -1, pointer: int = -1) -> None:
        self.list = wrapped if wrapped else []
        self.max_len = (
            len(self.list) if max_len < 0 or max_len > len(self.list) else max_len
        )
        self.selected = None
        self.start_rendering = 0
        self.end_rendering = self.max_len
        self.__pointer = -1
        if 0 <= pointer < len(self.list):
            self.pointer = pointer

    def __rich__(self) -> Text:
        content = Text(overflow="ignore")
        for index in range(self.start_rendering, self.end_rendering):
            item = self.list[index]
            string_index = str(index + 1)
            string_item = str(item)
            if self.selected == item:
                content.append(RIGHT_TRIANGLE, "green bold")
                content.append(" ")
                content.append(string_index, "purple bold")
                content.append(" ")
                content.append(string_item, "green bold")
            else:
                content.append("  ")
                content.append(string_index, "purple")
                content.append(" ")
                content.append(string_item)
            content.append("\n")
        return content

    def __str__(self) -> str:
        return str(self.renderables())

    def renderables(self) -> List[T]:
        return self.list[self.start_rendering : self.end_rendering]

    def reset(self) -> None:
        self.selected = None
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

        self.selected = self.list[self.__pointer]

    def previous(self) -> None:
        self.pointer -= 1

    def next(self) -> None:
        self.pointer += 1


if __name__ == "__main__":
    from rich.console import Console

    console = Console()
    items = ["item {}".format(n + 1) for n in list(range(5))]

    scrollable_list = ScrollableList(items, max_len=4, pointer=3)

    console.print("Default")
    print(scrollable_list)
    console.print(scrollable_list)

    console.print("Next")
    scrollable_list.next()
    print(scrollable_list)
    console.print(scrollable_list)

    console.print("Next")
    scrollable_list.next()
    print(scrollable_list)
    console.print(scrollable_list)

    console.print("Previous")
    scrollable_list.previous()
    print(scrollable_list)
    console.print(scrollable_list)

    console.print("Previous")
    scrollable_list.previous()
    print(scrollable_list)
    console.print(scrollable_list)

    console.print("Reset")
    scrollable_list.reset()
    print(scrollable_list)
    console.print(scrollable_list)
