"""Consumer group offset resets and deletion for admin mode.

Every method blocks on Kafka; callers run them through ``run_blocking``.
"""

from collections.abc import Mapping
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any

from confluent_kafka import ConsumerGroupTopicPartitions, KafkaException, TopicPartition
from confluent_kafka.admin import AdminClient, OffsetSpec

from kaskade.commands import OffsetTarget, ResetOffsetsCommand
from kaskade.timeouts import TimeoutConfig

NO_RECORD_FOR_TIMESTAMP = -1
"""The offset Kafka returns when no record is at or after the requested timestamp."""


class GroupNotEmptyError(Exception):
    """Kafka only resets offsets of, or deletes, a group without active members."""

    def __init__(self, group: str, members: int) -> None:
        noun = "member" if members == 1 else "members"
        super().__init__(f"Group '{group}' has {members} active {noun}; stop its consumers first")
        self.group = group
        self.members = members


@dataclass(frozen=True)
class OffsetReset:
    """One partition's committed offset, or ``None`` without one, and its new offset."""

    partition: int
    current: int | None
    new: int


@dataclass(frozen=True)
class OffsetResetPlan:
    """The exact offsets a reset commits, which the review shows before applying them."""

    group: str
    topic: str
    resets: tuple[OffsetReset, ...]


@dataclass(frozen=True)
class OffsetResetOutcome:
    partition: int
    offset: int
    error: str | None = None


class GroupService:
    def __init__(self, admin_client: AdminClient, *, timeouts: TimeoutConfig) -> None:
        self.admin_client = admin_client
        self.timeouts = timeouts

    def plan_reset(self, command: ResetOffsetsCommand) -> OffsetResetPlan:
        """Compute each partition's new offset, refusing a group with active members."""
        self.ensure_empty(command.group)
        partitions = [TopicPartition(command.topic, partition) for partition in command.partitions]
        current = self._committed_offsets(command.group, partitions)
        new = self._target_offsets(command, partitions)
        return OffsetResetPlan(
            command.group,
            command.topic,
            tuple(
                OffsetReset(partition.partition, current.get(partition.partition), new[index])
                for index, partition in enumerate(partitions)
            ),
        )

    def apply_reset(self, plan: OffsetResetPlan) -> tuple[OffsetResetOutcome, ...]:
        """Commit the planned offsets and return each partition's outcome."""
        request = ConsumerGroupTopicPartitions(
            plan.group,
            [TopicPartition(plan.topic, reset.partition, reset.new) for reset in plan.resets],
        )
        futures = self.admin_client.alter_consumer_group_offsets(
            [request], request_timeout=self.timeouts.admin_write
        )
        result = futures[plan.group].result()
        errors = {
            partition.partition: str(partition.error)
            for partition in result.topic_partitions or ()
            if partition.error is not None
        }
        return tuple(
            OffsetResetOutcome(reset.partition, reset.new, errors.get(reset.partition))
            for reset in plan.resets
        )

    def delete(self, group: str) -> None:
        """Delete a group without active members, with its offsets for every topic."""
        self.ensure_empty(group)
        futures = self.admin_client.delete_consumer_groups(
            [group], request_timeout=self.timeouts.admin_write
        )
        futures[group].result()

    def ensure_empty(self, group: str) -> None:
        futures = self.admin_client.describe_consumer_groups(
            [group], request_timeout=self.timeouts.admin_read
        )
        members = len(futures[group].result().members or ())
        if members:
            raise GroupNotEmptyError(group, members)

    def _committed_offsets(self, group: str, partitions: list[TopicPartition]) -> dict[int, int]:
        futures = self.admin_client.list_consumer_group_offsets(
            [ConsumerGroupTopicPartitions(group, partitions)],
            request_timeout=self.timeouts.admin_read,
        )
        result = futures[group].result()
        committed: dict[int, int] = {}
        for partition in result.topic_partitions or ():
            if partition.error is not None:
                raise KafkaException(partition.error)
            if partition.offset >= 0:
                committed[partition.partition] = partition.offset
        return committed

    def _target_offsets(
        self, command: ResetOffsetsCommand, partitions: list[TopicPartition]
    ) -> list[int]:
        if command.target is OffsetTarget.EARLIEST:
            return self._list_offsets(partitions, OffsetSpec.earliest())  # type: ignore[no-untyped-call]
        latest = self._list_offsets(partitions, OffsetSpec.latest())  # type: ignore[no-untyped-call]
        if command.target is OffsetTarget.LATEST:
            return latest
        if command.target is OffsetTarget.TIMESTAMP:
            found = self._list_offsets(partitions, OffsetSpec.for_timestamp(command.value))
            return [
                end if offset == NO_RECORD_FOR_TIMESTAMP else offset
                for offset, end in zip(found, latest, strict=True)
            ]
        # Like kafka-consumer-groups, keep an explicit offset within each partition's records.
        earliest = self._list_offsets(partitions, OffsetSpec.earliest())  # type: ignore[no-untyped-call]
        return [
            min(max(command.value, start), end) for start, end in zip(earliest, latest, strict=True)
        ]

    def _list_offsets(self, partitions: list[TopicPartition], spec: Any) -> list[int]:
        futures: Mapping[Any, Future[Any]] = self.admin_client.list_offsets(
            dict.fromkeys(partitions, spec),
            request_timeout=self.timeouts.admin_read,
        )
        results = {
            (partition.topic, partition.partition): future.result().offset
            for partition, future in futures.items()
        }
        return [results[(partition.topic, partition.partition)] for partition in partitions]
