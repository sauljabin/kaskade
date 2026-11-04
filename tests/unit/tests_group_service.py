import unittest
from typing import Any
from unittest.mock import MagicMock

from confluent_kafka import (
    ConsumerGroupTopicPartitions,
    KafkaError,
    KafkaException,
    TopicPartition,
)
from confluent_kafka.admin import ListOffsetsResultInfo

from kaskade.commands import OffsetTarget, ResetOffsetsCommand
from kaskade.group_service import (
    GroupNotEmptyError,
    GroupService,
    OffsetReset,
    OffsetResetOutcome,
    OffsetResetPlan,
)
from kaskade.timeouts import TimeoutConfig
from tests import completed, failed


def admin_client(
    *,
    members: int = 0,
    committed: dict[int, int] | None = None,
    earliest: dict[int, int] | None = None,
    latest: dict[int, int] | None = None,
    at_timestamp: dict[int, int] | None = None,
) -> MagicMock:
    """Return an admin client double for group 'billing' and topic 'orders'."""
    admin = MagicMock()
    description = MagicMock(members=[MagicMock() for _ in range(members)])
    admin.describe_consumer_groups.return_value = {"billing": completed(description)}
    admin.list_consumer_group_offsets.return_value = {
        "billing": completed(
            ConsumerGroupTopicPartitions(
                "billing",
                [
                    TopicPartition("orders", partition, offset)
                    for partition, offset in (committed or {}).items()
                ],
            )
        )
    }

    def list_offsets(request: dict[TopicPartition, Any], **_: Any) -> dict[Any, Any]:
        spec = type(next(iter(request.values()))).__name__
        offsets = {"EarliestSpec": earliest, "LatestSpec": latest}.get(spec, at_timestamp) or {}
        return {
            partition: completed(ListOffsetsResultInfo(offsets[partition.partition], -1, -1))
            for partition in request
        }

    admin.list_offsets.side_effect = list_offsets
    return admin


def service(admin: MagicMock) -> GroupService:
    return GroupService(admin, timeouts=TimeoutConfig())


def command(target: OffsetTarget, value: int = 0) -> ResetOffsetsCommand:
    return ResetOffsetsCommand("billing", "orders", (0, 1), target, value)


class TestPlanReset(unittest.TestCase):
    def test_plans_each_target_with_current_offsets(self) -> None:
        admin = admin_client(
            committed={0: 7},
            earliest={0: 2, 1: 3},
            latest={0: 10, 1: 20},
            at_timestamp={0: 5, 1: -1},
        )
        cases = (
            (command(OffsetTarget.EARLIEST), (2, 3)),
            (command(OffsetTarget.LATEST), (10, 20)),
            (command(OffsetTarget.TIMESTAMP, 1_700_000_000_000), (5, 20)),
            (command(OffsetTarget.OFFSET, 15), (10, 15)),
            (command(OffsetTarget.OFFSET, 0), (2, 3)),
        )

        for reset_command, (first, second) in cases:
            with self.subTest(target=reset_command.target, value=reset_command.value):
                self.assertEqual(
                    OffsetResetPlan(
                        "billing",
                        "orders",
                        (OffsetReset(0, 7, first), OffsetReset(1, None, second)),
                    ),
                    service(admin).plan_reset(reset_command),
                )

    def test_refuses_a_group_with_active_members_before_reading_offsets(self) -> None:
        admin = admin_client(members=2)

        with self.assertRaisesRegex(GroupNotEmptyError, "Group 'billing' has 2 active members"):
            service(admin).plan_reset(command(OffsetTarget.EARLIEST))

        admin.list_consumer_group_offsets.assert_not_called()
        admin.list_offsets.assert_not_called()

    def test_reports_authorization_failures(self) -> None:
        admin = admin_client()
        admin.describe_consumer_groups.return_value = {
            "billing": failed(KafkaException(KafkaError(KafkaError.GROUP_AUTHORIZATION_FAILED)))
        }

        with self.assertRaises(KafkaException):
            service(admin).plan_reset(command(OffsetTarget.EARLIEST))

    def test_reports_committed_offset_partition_errors(self) -> None:
        admin = admin_client()
        partition = MagicMock(
            topic="orders", partition=0, error=KafkaError(KafkaError.TOPIC_AUTHORIZATION_FAILED)
        )
        admin.list_consumer_group_offsets.return_value = {
            "billing": completed(MagicMock(topic_partitions=[partition]))
        }

        with self.assertRaises(KafkaException):
            service(admin).plan_reset(command(OffsetTarget.EARLIEST))


class TestApplyReset(unittest.TestCase):
    def test_commits_the_planned_offsets_and_reports_each_partition(self) -> None:
        admin = MagicMock()
        rejected = MagicMock(
            topic="orders",
            partition=1,
            offset=4,
            error=KafkaError(KafkaError.TOPIC_AUTHORIZATION_FAILED),
        )
        admin.alter_consumer_group_offsets.return_value = {
            "billing": completed(
                MagicMock(topic_partitions=[TopicPartition("orders", 0, 2), rejected])
            )
        }
        plan = OffsetResetPlan("billing", "orders", (OffsetReset(0, 7, 2), OffsetReset(1, None, 4)))

        outcomes = service(admin).apply_reset(plan)

        (request,) = admin.alter_consumer_group_offsets.call_args.args[0]
        self.assertEqual("billing", request.group_id)
        self.assertEqual(
            [("orders", 0, 2), ("orders", 1, 4)],
            [(item.topic, item.partition, item.offset) for item in request.topic_partitions],
        )
        self.assertEqual(OffsetResetOutcome(0, 2), outcomes[0])
        self.assertEqual(1, outcomes[1].partition)
        self.assertIsNotNone(outcomes[1].error)


class TestDeleteGroup(unittest.TestCase):
    def test_deletes_an_empty_group(self) -> None:
        admin = admin_client()
        admin.delete_consumer_groups.return_value = {"billing": completed(None)}

        service(admin).delete("billing")

        self.assertEqual(["billing"], admin.delete_consumer_groups.call_args.args[0])

    def test_refuses_a_group_with_active_members(self) -> None:
        admin = admin_client(members=1)

        with self.assertRaisesRegex(GroupNotEmptyError, "1 active member;"):
            service(admin).delete("billing")

        admin.delete_consumer_groups.assert_not_called()


if __name__ == "__main__":
    unittest.main()
