import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from confluent_kafka.serialization import MessageField
from google.protobuf.message import DecodeError

from kaskade.deserializers import (
    AvroDeserializer,
    BooleanDeserializer,
    BytesEncoding,
    DefaultDeserializer,
    Deserialization,
    DeserializationError,
    DeserializerPool,
    DoubleDeserializer,
    FloatDeserializer,
    IntegerDeserializer,
    JsonDeserializer,
    LongDeserializer,
    ProtobufDeserializer,
    RegistryDeserializer,
    StringDeserializer,
)
from kaskade.models import Header, Record
from kaskade.record_export import record_json
from kaskade.utils import file_to_str, py_to_avro
from tests import faker
from tests.unit.protobuf_model.user_pb2 import User

UNIT_TESTS_PATH = Path(__file__).resolve().parent
DESCRIPTOR_PATH = str(UNIT_TESTS_PATH / "protobuf_model" / "user.desc")
AVRO_PATH = str(UNIT_TESTS_PATH / "avro_model" / "user.avsc")


class TestDeserializer(unittest.TestCase):
    def test_missing_deserializer_configuration_raises_deserialization_error(self):
        pool = DeserializerPool()

        missing_configurations = {
            Deserialization.REGISTRY: "Schema Registry is not configured",
            Deserialization.AVRO: "Avro is not configured",
            Deserialization.PROTOBUF: "Protobuf is not configured",
        }
        for deserialization, message in missing_configurations.items():
            with (
                self.subTest(deserialization=deserialization),
                self.assertRaisesRegex(DeserializationError, message),
            ):
                pool.get(deserialization)

    def test_pool_reuses_configured_deserializers(self):
        pool = DeserializerPool()

        self.assertIs(pool.get(Deserialization.STRING), pool.get(Deserialization.STRING))
        self.assertIs(pool.default_deserializer, pool.get(Deserialization.BYTES))

    def test_header_falls_back_to_binary_value_for_deserialization_error(self):
        value = b"invalid"
        deserializer = MagicMock()
        deserializer.deserialize.side_effect = DeserializationError("invalid data")
        header = Header(value=value, value_deserializer=deserializer)

        self.assertEqual(value, header.value_deserialized())
        self.assertEqual(value, header.value_deserialized())
        self.assertEqual("aW52YWxpZA==", header.value_str())
        self.assertEqual(
            {
                "key": "",
                "value": "aW52YWxpZA==",
                "error": {
                    "message": "invalid data",
                    "fallback": {"type": "BYTES", "encoding": "BASE64"},
                },
            },
            header.dict(),
        )
        deserializer.deserialize.assert_called_once_with(value)

    def test_header_falls_back_for_malformed_integer(self):
        value = b"586"
        header = Header(value=value, value_deserializer=IntegerDeserializer())

        self.assertEqual(value, header.value_deserialized())

    def test_header_keeps_valid_and_null_values_minimal(self):
        deserializer = StringDeserializer()

        self.assertEqual(
            {"key": "source", "value": "storefront"},
            Header("source", b"storefront", deserializer).dict(),
        )
        self.assertEqual(
            {"key": "nullable", "value": None},
            Header("nullable", None, deserializer).dict(),
        )

    def test_null_content_uses_json_literal_for_display(self):
        record = Record()
        header = Header("nullable", None)

        self.assertEqual("null", record.key_str())
        self.assertEqual("null", record.value_str())
        self.assertEqual("null", header.value_str())
        self.assertEqual("nullable:null", str(header))

    def test_record_caches_successful_deserialization(self):
        key_deserializer = MagicMock()
        key_deserializer.deserialize.return_value = "customer-1"
        value_deserializer = MagicMock()
        value_deserializer.deserialize.return_value = {"total": 10}
        record = Record(
            topic="orders",
            key=b"customer-1",
            value=b"payload",
            key_deserializer=key_deserializer,
            value_deserializer=value_deserializer,
        )

        self.assertEqual("customer-1", record.key_str())
        self.assertEqual("customer-1", record.key_str())
        self.assertEqual("{'total': 10}", record.value_str())
        self.assertEqual("{'total': 10}", record.value_str())
        key_deserializer.deserialize.assert_called_once()
        value_deserializer.deserialize.assert_called_once()

    def test_record_boolean_strings_use_json_literals(self):
        deserializer = BooleanDeserializer()
        record = Record(
            key=struct.pack(">?", False),
            value=struct.pack(">?", True),
            key_deserializer=deserializer,
            value_deserializer=deserializer,
        )

        self.assertEqual("false", record.key_str())
        self.assertEqual("true", record.value_str())
        self.assertIs(record.dict()["key"]["content"], False)
        self.assertIs(record.dict()["value"]["content"], True)

    def test_record_bytes_support_every_output_encoding(self):
        data = b"Hello world"
        encodings = {
            BytesEncoding.BASE64: ("SGVsbG8gd29ybGQ=", "SGVsbG8gd29ybGQ="),
            BytesEncoding.HEX: ("48656c6c6f20776f726c64", "48656c6c6f20776f726c64"),
            BytesEncoding.BYTE_ARRAY: (
                [72, 101, 108, 108, 111, 32, 119, 111, 114, 108, 100],
                "[72, 101, 108, 108, 111, 32, 119, 111, 114, 108, 100]",
            ),
            BytesEncoding.ESCAPED: ("Hello world", "Hello world"),
        }

        for bytes_encoding, (json_data, display) in encodings.items():
            record = Record(key=data, key_bytes_encoding=bytes_encoding)

            with self.subTest(bytes_encoding=bytes_encoding):
                self.assertEqual(
                    json_data,
                    record.dict()["key"]["content"],
                )
                self.assertEqual(
                    {"type": "BYTES", "encoding": bytes_encoding.name},
                    record.dict()["key"]["deserializer"],
                )
                self.assertEqual(
                    record.dict(),
                    json.loads(record_json(record)),
                )
                self.assertEqual(display, record.key_str())

    def test_escaped_bytes_are_language_neutral(self):
        record = Record(
            key=b"Hello\\world\x00\n\xff",
            key_bytes_encoding=BytesEncoding.ESCAPED,
        )

        self.assertEqual(r"Hello\\world\x00\x0a\xff", record.key_str())
        self.assertEqual(r"Hello\\world\x00\x0a\xff", record.dict()["key"]["content"])

    def test_null_content_omits_schema_and_bytes_encoding_for_every_deserializer(self):
        for deserialization in Deserialization:
            with self.subTest(deserialization=deserialization):
                field = Record(key_deserialization=deserialization).dict()["key"]

                self.assertEqual(
                    {
                        "content": None,
                        "deserializer": {"type": deserialization.name},
                    },
                    field,
                )

    def test_record_propagates_unexpected_deserialization_errors(self):
        for exception in (RuntimeError("unexpected"), IndexError("unexpected")):
            deserializer = MagicMock()
            deserializer.deserialize.side_effect = exception
            record = Record(key=b"payload", key_deserializer=deserializer)

            with (
                self.subTest(exception=type(exception).__name__),
                self.assertRaisesRegex(type(exception), "unexpected"),
            ):
                record.key_str()

    def test_record_falls_back_for_malformed_integer(self):
        record = Record(
            topic="integer",
            key=b"586",
            key_deserialization=Deserialization.INTEGER,
            key_deserializer=IntegerDeserializer(),
            key_bytes_encoding=BytesEncoding.HEX,
        )

        self.assertEqual(
            {
                "content": "NTg2",
                "deserializer": {"type": "INTEGER"},
                "error": {
                    "message": "unpack requires a buffer of 4 bytes",
                    "fallback": {"type": "BYTES", "encoding": "BASE64"},
                },
            },
            record.dict()["key"],
        )

    def test_header_propagates_unexpected_errors(self):
        deserializer = MagicMock()
        deserializer.deserialize.side_effect = RuntimeError("unexpected")
        header = Header(value=b"invalid", value_deserializer=deserializer)

        with self.assertRaisesRegex(RuntimeError, "unexpected"):
            header.value_deserialized()

    def test_string_deserialization(self):
        expected_value = faker.word()
        deserializer = StringDeserializer()

        result = deserializer.deserialize(expected_value.encode("utf-8"))

        self.assertEqual(expected_value, result)

    def test_integer_deserialization(self):
        expected_value = faker.random_int(10, 100)
        deserializer = IntegerDeserializer()

        result = deserializer.deserialize(struct.pack(">i", expected_value))

        self.assertEqual(expected_value, result)

    def test_fixed_width_deserializers_normalize_invalid_payload_size(self):
        deserializers = (
            BooleanDeserializer(),
            IntegerDeserializer(),
            LongDeserializer(),
            FloatDeserializer(),
            DoubleDeserializer(),
        )

        for deserializer in deserializers:
            with (
                self.subTest(deserializer=type(deserializer).__name__),
                self.assertRaisesRegex(DeserializationError, "unpack requires") as raised,
            ):
                deserializer.deserialize(b"586")

            self.assertIsInstance(raised.exception.__cause__, struct.error)

    def test_default_deserialization(self):
        expected_value = os.urandom(10)
        deserializer = DefaultDeserializer()

        result = deserializer.deserialize(expected_value)

        self.assertEqual(expected_value, result)

    def test_boolean_deserialization(self):
        expected_value = faker.pybool()
        deserializer = BooleanDeserializer()

        result = deserializer.deserialize(struct.pack(">?", expected_value))

        self.assertEqual(expected_value, result)

    def test_long_deserialization(self):
        expected_value = faker.pyint()
        deserializer = LongDeserializer()

        result = deserializer.deserialize(struct.pack(">q", expected_value))

        self.assertEqual(expected_value, result)

    def test_double_deserialization(self):
        expected_value = faker.pyfloat()
        deserializer = DoubleDeserializer()

        result = deserializer.deserialize(struct.pack(">d", expected_value))

        self.assertEqual(expected_value, result)

    def test_float_deserialization(self):
        expected_value = faker.pyfloat(positive=True, min_value=10, max_value=100, right_digits=2)
        deserializer = FloatDeserializer()

        result = deserializer.deserialize(struct.pack(">f", expected_value))

        self.assertEqual(round(expected_value, 2), round(result, 2))

    def test_json_deserialization(self):
        expected_value = faker.pydict(5, value_types=[str, int, float, bool])
        deserializer = JsonDeserializer()

        result = deserializer.deserialize(json.dumps(expected_value).encode("utf-8"))

        self.assertEqual(expected_value, result)

    def test_json_deserialization_with_magic_byte(self):
        expected_value = faker.pydict(5, value_types=[str, int, float, bool])
        deserializer = JsonDeserializer({"framing": "confluent"})

        binaries = b"\x00\x00\x00\x00\x00" + json.dumps(expected_value).encode("utf-8")
        result = deserializer.deserialize(binaries)

        self.assertEqual(expected_value, result)

    def test_json_raw_framing_does_not_infer_confluent_header(self):
        payload = b"\x00\x00\x00\x00\x01{}"

        with self.assertRaises((UnicodeDecodeError, json.JSONDecodeError)):
            JsonDeserializer().deserialize(payload, "orders", MessageField.VALUE)

    def test_json_framing_can_differ_between_key_and_value(self):
        expected_value = {"active": True}
        encoded = json.dumps(expected_value).encode("utf-8")
        deserializer = JsonDeserializer(
            {
                "framing": "confluent",
                "key.framing": "raw",
            }
        )

        self.assertEqual(
            expected_value,
            deserializer.deserialize(encoded, "orders", MessageField.KEY),
        )
        self.assertEqual(
            expected_value,
            deserializer.deserialize(
                b"\x00\x00\x00\x00\x01" + encoded,
                "orders",
                MessageField.VALUE,
            ),
        )

    @patch("kaskade.deserializers.SchemaRegistryClient")
    def test_registry_deserialization_avro(self, mock_sr_client_class):
        expected_value = {"name": "Pedro Pascal"}

        mock_sr_client_class.return_value.get_schema.return_value.schema_str = file_to_str(
            AVRO_PATH
        )
        mock_sr_client_class.return_value.get_schema.return_value.schema_type = "AVRO"

        encoded = py_to_avro(AVRO_PATH, expected_value)

        deserializer = RegistryDeserializer({})

        result = deserializer.deserialize(b"\x00\x00\x00\x00\x00" + encoded, "", MessageField.VALUE)

        self.assertEqual(expected_value, result)

    @patch("kaskade.deserializers.SchemaRegistryClient")
    def test_registry_avro_normalizes_corrupt_payload_error(self, mock_sr_client_class):
        schema = mock_sr_client_class.return_value.get_schema.return_value
        schema.schema_str = file_to_str(AVRO_PATH)
        schema.schema_type = "AVRO"
        deserializer = RegistryDeserializer({})

        with self.assertRaises(DeserializationError) as raised:
            deserializer.deserialize(
                b"\x00\x00\x00\x00\x00\xff",
                "orders",
                MessageField.VALUE,
            )

        self.assertIsInstance(raised.exception.__cause__, IndexError)

    @patch("kaskade.deserializers.SchemaRegistryClient")
    def test_registry_deserialization_json(self, mock_sr_client_class):
        expected_value = {"name": "Pedro Pascal"}
        expected_json = json.dumps(expected_value)

        mock_sr_client_class.return_value.get_schema.return_value.schema_str = expected_json
        mock_sr_client_class.return_value.get_schema.return_value.schema_type = "JSON"

        deserializer = RegistryDeserializer({})

        result = deserializer.deserialize(
            b"\x00\x00\x00\x00\x00" + expected_json.encode(), "", MessageField.VALUE
        )

        self.assertEqual(expected_value, result)

    @patch("kaskade.deserializers.SchemaRegistryClient")
    def test_registry_metadata_uses_a_unique_registration_and_caches_it(self, mock_sr_client_class):
        registry_client = mock_sr_client_class.return_value
        registry_client.get_schema.return_value.schema_type = "JSON"
        registry_client.get_schema_versions.return_value = [
            SimpleNamespace(subject="orders-key", version=2)
        ]
        deserializer = RegistryDeserializer({})
        deserializer.json_deserializer = MagicMock(return_value={"id": "order-1049"})
        payload = b"\x00\x00\x00\x00\x0c{}"

        first = deserializer.deserialize_with_metadata(payload, "orders", MessageField.KEY)
        second = deserializer.deserialize_with_metadata(payload, "orders", MessageField.KEY)

        self.assertEqual({"id": "order-1049"}, first.content)
        self.assertEqual(first, second)
        self.assertIsNotNone(first.schema)
        self.assertEqual(
            {
                "id": 12,
                "subject": "orders-key",
                "version": 2,
                "type": "JSON",
            },
            first.schema.dict(),
        )
        registry_client.get_schema_versions.assert_called_once_with(12)

    @patch("kaskade.deserializers.SchemaRegistryClient")
    def test_registry_metadata_prefers_the_conventional_field_subject(self, mock_sr_client_class):
        registry_client = mock_sr_client_class.return_value
        registry_client.get_schema.return_value.schema_type = "AVRO"
        registry_client.get_schema_versions.return_value = [
            SimpleNamespace(subject="shared-order", version=1),
            SimpleNamespace(subject="orders-value", version=5),
        ]
        deserializer = RegistryDeserializer({})
        deserializer.avro_deserializer = MagicMock(return_value={"status": "shipped"})

        result = deserializer.deserialize_with_metadata(
            b"\x00\x00\x00\x00\x1bpayload",
            "orders",
            MessageField.VALUE,
        )

        self.assertIsNotNone(result.schema)
        self.assertEqual("orders-value", result.schema.subject)
        self.assertEqual(5, result.schema.version)

    @patch("kaskade.deserializers.SchemaRegistryClient")
    def test_registry_metadata_is_null_when_registrations_are_ambiguous(self, mock_sr_client_class):
        registry_client = mock_sr_client_class.return_value
        registry_client.get_schema.return_value.schema_type = "JSON"
        registry_client.get_schema_versions.return_value = [
            SimpleNamespace(subject="shared-one", version=1),
            SimpleNamespace(subject="shared-two", version=2),
        ]
        deserializer = RegistryDeserializer({})
        deserializer.json_deserializer = MagicMock(return_value={"status": "paid"})

        result = deserializer.deserialize_with_metadata(
            b"\x00\x00\x00\x00\x1b{}",
            "orders",
            MessageField.VALUE,
        )

        self.assertEqual({"status": "paid"}, result.content)
        self.assertIsNone(result.schema)

    @patch("kaskade.deserializers.SchemaRegistryClient")
    def test_registry_metadata_lookup_failure_does_not_fail_deserialization(
        self, mock_sr_client_class
    ):
        registry_client = mock_sr_client_class.return_value
        registry_client.get_schema.return_value.schema_type = "JSON"
        registry_client.get_schema_versions.side_effect = OSError("registry unavailable")
        deserializer = RegistryDeserializer({})
        deserializer.json_deserializer = MagicMock(return_value={"status": "paid"})

        with self.assertLogs("kaskade", level="WARNING"):
            result = deserializer.deserialize_with_metadata(
                b"\x00\x00\x00\x00\x1b{}",
                "orders",
                MessageField.VALUE,
            )

        self.assertEqual({"status": "paid"}, result.content)
        self.assertIsNone(result.schema)

    def test_protobuf_deserialization(self):
        deserializer = ProtobufDeserializer({"descriptor": DESCRIPTOR_PATH, "value": "User"})

        user = User()
        user.name = "my name"

        result = deserializer.deserialize(user.SerializeToString(), "", MessageField.VALUE)
        self.assertEqual({"name": user.name}, result)

    def test_protobuf_deserialization_with_magic_byte(self):
        deserializer = ProtobufDeserializer(
            {
                "descriptor": DESCRIPTOR_PATH,
                "value": "User",
                "framing": "confluent",
            }
        )

        user = User()
        user.name = "my name"

        result = deserializer.deserialize(
            b"\x00\x00\x00\x00\x00\x00" + user.SerializeToString(), "", MessageField.VALUE
        )
        self.assertEqual({"name": user.name}, result)

    def test_protobuf_raw_framing_does_not_infer_confluent_header(self):
        user = User(name="my name")
        payload = b"\x00\x00\x00\x00\x01\x00" + user.SerializeToString()
        deserializer = ProtobufDeserializer({"descriptor": DESCRIPTOR_PATH, "value": "User"})

        with self.assertRaises(DecodeError):
            deserializer.deserialize(payload, "orders", MessageField.VALUE)

    def test_protobuf_framing_can_differ_between_key_and_value(self):
        deserializer = ProtobufDeserializer(
            {
                "descriptor": DESCRIPTOR_PATH,
                "key": "User",
                "value": "User",
                "framing": "confluent",
                "key.framing": "raw",
            }
        )
        user = User(name="my name")

        self.assertEqual(
            {"name": user.name},
            deserializer.deserialize(user.SerializeToString(), "orders", MessageField.KEY),
        )
        self.assertEqual(
            {"name": user.name},
            deserializer.deserialize(
                b"\x00\x00\x00\x00\x01\x00" + user.SerializeToString(),
                "orders",
                MessageField.VALUE,
            ),
        )

    def test_avro_deserialization(self):
        expected_value = {"name": "Pedro Pascal"}
        deserializer = AvroDeserializer({"value": AVRO_PATH})
        encoded = py_to_avro(AVRO_PATH, expected_value)

        result = deserializer.deserialize(encoded, "", MessageField.VALUE)
        self.assertEqual(expected_value, result)

    def test_avro_normalizes_corrupt_payload_error(self):
        deserializer = AvroDeserializer({"value": AVRO_PATH})

        with self.assertRaises(DeserializationError) as raised:
            deserializer.deserialize(b"\xff", "orders", MessageField.VALUE)

        self.assertIsInstance(raised.exception.__cause__, IndexError)

    def test_avro_deserialization_with_magic_byte(self):
        expected_value = {"name": "Pedro Pascal"}
        deserializer = AvroDeserializer({"value": AVRO_PATH, "framing": "confluent"})
        encoded = py_to_avro(AVRO_PATH, expected_value)

        result = deserializer.deserialize(b"\x00\x00\x00\x00\x00" + encoded, "", MessageField.VALUE)

        self.assertEqual(expected_value, result)

    def test_avro_framing_can_differ_between_key_and_value(self):
        expected_value = {"name": "Pedro Pascal"}
        encoded = py_to_avro(AVRO_PATH, expected_value)
        deserializer = AvroDeserializer(
            {
                "key": AVRO_PATH,
                "value": AVRO_PATH,
                "framing": "confluent",
                "key.framing": "raw",
            }
        )

        self.assertEqual(
            expected_value,
            deserializer.deserialize(encoded, "orders", MessageField.KEY),
        )
        self.assertEqual(
            expected_value,
            deserializer.deserialize(
                b"\x00\x00\x00\x00\x01" + encoded,
                "orders",
                MessageField.VALUE,
            ),
        )

    def test_raw_avro_starting_with_zero_is_not_mistaken_for_framing(self):
        schema = {
            "name": "Sample",
            "type": "record",
            "fields": [
                {"name": "count", "type": "int"},
                {"name": "description", "type": "string"},
            ],
        }
        expected_value = {"count": 0, "description": "long enough payload"}
        with tempfile.TemporaryDirectory() as directory:
            schema_path = Path(directory) / "sample.avsc"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            encoded = py_to_avro(str(schema_path), expected_value)

            self.assertEqual(0, encoded[0])
            self.assertGreater(len(encoded), 5)
            result = AvroDeserializer({"value": str(schema_path)}).deserialize(
                encoded,
                "",
                MessageField.VALUE,
            )

        self.assertEqual(expected_value, result)


if __name__ == "__main__":
    unittest.main()
