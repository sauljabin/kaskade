import unittest
from unittest.mock import MagicMock

from confluent_kafka import KafkaException

from kaskade.deserializers import Deserialization
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


class TestRecordDeserializationFallback(unittest.TestCase):
    def _failing_deserializer(self) -> MagicMock:
        deserializer = MagicMock()
        deserializer.deserialize.side_effect = ValueError("malformed payload")
        return deserializer

    def test_key_failure_falls_back_to_bytes_and_keeps_the_value(self) -> None:
        value_deserializer = MagicMock()
        value_deserializer.deserialize.return_value = "paid"
        record = Record(
            topic="orders",
            partition=0,
            offset=1,
            key=b"bad-key",
            value=b"paid",
            key_deserializer=self._failing_deserializer(),
            value_deserializer=value_deserializer,
        )

        self.assertEqual(str(b"bad-key"), record.key_str())
        self.assertEqual("paid", record.value_str())
        self.assertEqual("malformed payload", record.key_error())
        self.assertIsNone(record.value_error())
        self.assertTrue(record.has_deserialization_errors())

    def test_value_failure_falls_back_to_bytes_and_keeps_the_key(self) -> None:
        key_deserializer = MagicMock()
        key_deserializer.deserialize.return_value = "order-1"
        record = Record(
            topic="orders",
            partition=0,
            offset=1,
            key=b"order-1",
            value=b"bad-value",
            key_deserializer=key_deserializer,
            value_deserializer=self._failing_deserializer(),
        )

        self.assertEqual("order-1", record.key_str())
        self.assertEqual(str(b"bad-value"), record.value_str())
        self.assertIsNone(record.key_error())
        self.assertEqual("malformed payload", record.value_error())
        self.assertTrue(record.has_deserialization_errors())

    def test_no_errors_when_both_fields_deserialize_successfully(self) -> None:
        key_deserializer = MagicMock()
        key_deserializer.deserialize.return_value = "order-1"
        value_deserializer = MagicMock()
        value_deserializer.deserialize.return_value = "paid"
        record = Record(
            topic="orders",
            partition=0,
            offset=1,
            key=b"order-1",
            value=b"paid",
            key_deserializer=key_deserializer,
            value_deserializer=value_deserializer,
        )

        self.assertFalse(record.has_deserialization_errors())
        self.assertIsNone(record.key_error())
        self.assertIsNone(record.value_error())

    def test_dict_includes_fallback_metadata_only_for_the_failed_field(self) -> None:
        value_deserializer = MagicMock()
        value_deserializer.deserialize.return_value = "paid"
        record = Record(
            topic="orders",
            partition=0,
            offset=1,
            key=b"bad-key",
            value=b"paid",
            key_deserialization=Deserialization.JSON,
            value_deserialization=Deserialization.JSON,
            key_deserializer=self._failing_deserializer(),
            value_deserializer=value_deserializer,
        )

        data = record.dict()

        self.assertEqual(
            {
                "deserializer": "JSON",
                "content": str(b"bad-key"),
                "fallback": "BYTES",
                "error": "malformed payload",
            },
            data["key"],
        )
        self.assertEqual({"deserializer": "JSON", "content": "paid"}, data["value"])

    def test_deserialization_is_only_attempted_once_per_field(self) -> None:
        deserializer = self._failing_deserializer()
        record = Record(topic="orders", partition=0, offset=1, key=b"bad-key")
        record.key_deserializer = deserializer

        record.key_str()
        record.key_str()
        record.key_error()
        record.dict()

        self.assertEqual(1, deserializer.deserialize.call_count)

    def test_unrecognized_exceptions_are_not_treated_as_fallbacks(self) -> None:
        deserializer = MagicMock()
        deserializer.deserialize.side_effect = KafkaException("broker unavailable")
        record = Record(
            topic="orders", partition=0, offset=1, key=b"key", key_deserializer=deserializer
        )

        with self.assertRaises(KafkaException):
            record.key_str()


if __name__ == "__main__":
    unittest.main()
