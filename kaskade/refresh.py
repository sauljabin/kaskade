from dataclasses import dataclass
from enum import Enum, auto


class RefreshReason(Enum):
    INITIAL = auto()
    MANUAL = auto()
    PERIODIC = auto()
    RESUME = auto()
    MUTATION = auto()
    PENDING = auto()


@dataclass
class RefreshCoordinator:
    generation: int = 0
    active: bool = False
    pending: bool = False
    mutation_active: bool = False

    def request(self, reason: RefreshReason) -> int | None:
        if self.active or self.mutation_active:
            if reason is not RefreshReason.PERIODIC:
                self.pending = True
            return None
        self.generation += 1
        self.active = True
        return self.generation

    def is_current(self, generation: int) -> bool:
        return self.active and generation == self.generation

    def complete(self, generation: int) -> bool:
        if not self.is_current(generation):
            return False
        self.active = False
        return True

    def take_pending(self) -> bool:
        if not self.pending or self.active or self.mutation_active:
            return False
        self.pending = False
        return True

    def begin_mutation(self) -> None:
        self.mutation_active = True

    def end_mutation(self) -> None:
        self.mutation_active = False

    def discard_pending(self) -> None:
        self.pending = False
