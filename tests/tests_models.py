import unittest

from kaskade.models import GroupMember, GroupPartition, Header, Partition, Record


class TestModelIdentity(unittest.TestCase):
    def test_partition_identity_includes_topic(self) -> None:
        self.assertNotEqual(Partition(id=0, topic="orders"), Partition(id=0, topic="payments"))

    def test_group_entities_include_parent_identity(self) -> None:
        self.assertNotEqual(
            GroupMember(id="member", group="alpha"),
            GroupMember(id="member", group="bravo"),
        )
        self.assertNotEqual(
            GroupPartition(id=0, topic="orders", group="alpha"),
            GroupPartition(id=0, topic="orders", group="bravo"),
        )

    def test_record_identity_includes_topic(self) -> None:
        self.assertNotEqual(
            Record(topic="orders", partition=0, offset=1),
            Record(topic="payments", partition=0, offset=1),
        )

    def test_header_identity_includes_value(self) -> None:
        self.assertNotEqual(Header("source", b"web"), Header("source", b"mobile"))


if __name__ == "__main__":
    unittest.main()
