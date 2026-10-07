from collections import OrderedDict
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class LruCache(Generic[K, V]):
    """Keeps at most `capacity` entries and evicts the least recently used one."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self._items: OrderedDict[K, V] = OrderedDict()

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, key: object) -> bool:
        return key in self._items

    def get(self, key: K) -> V | None:
        if key not in self._items:
            return None
        self._items.move_to_end(key)
        return self._items[key]

    def put(self, key: K, value: V) -> None:
        self._items[key] = value
        self._items.move_to_end(key)
        while len(self._items) > self.capacity:
            self._items.popitem(last=False)

    def remove(self, key: K) -> None:
        self._items.pop(key, None)
