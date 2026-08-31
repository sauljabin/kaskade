import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from confluent_kafka.serialization import MessageField

from kaskade.deserializers import (
    AvroDeserializer,
    BooleanDeserializer,
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

        self.assertEqual(str(value), header.value_deserialized())
        self.assertEqual(str(value), header.value_deserialized())
        deserializer.deserialize.assert_called_once_with(value)

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

    def test_record_propagates_unexpected_deserialization_errors(self):
        deserializer = MagicMock()
        deserializer.deserialize.side_effect = RuntimeError("unexpected")
        record = Record(key=b"payload", key_deserializer=deserializer)

        with self.assertRaisesRegex(RuntimeError, "unexpected"):
            record.key_str()

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

    def test_default_deserialization(self):
        expected_value = os.urandom(10)
        deserializer = DefaultDeserializer()

        result = deserializer.deserialize(expected_value)

        self.assertEqual(str(expected_value), result)

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
        deserializer = JsonDeserializer()

        binaries = b"\x00\x00\x00\x00\x00" + json.dumps(expected_value).encode("utf-8")
        result = deserializer.deserialize(binaries)

        self.assertEqual(expected_value, result)

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

    def test_protobuf_deserialization(self):
        deserializer = ProtobufDeserializer({"descriptor": DESCRIPTOR_PATH, "value": "User"})

        user = User()
        user.name = "my name"

        result = deserializer.deserialize(user.SerializeToString(), "", MessageField.VALUE)
        self.assertEqual({"name": user.name}, result)

    def test_protobuf_deserialization_with_magic_byte(self):
        deserializer = ProtobufDeserializer({"descriptor": DESCRIPTOR_PATH, "value": "User"})

        user = User()
        user.name = "my name"

        result = deserializer.deserialize(
            b"\x00\x00\x00\x00\x00\x00" + user.SerializeToString(), "", MessageField.VALUE
        )
        self.assertEqual({"name": user.name}, result)

    def test_avro_deserialization(self):
        expected_value = {"name": "Pedro Pascal"}
        deserializer = AvroDeserializer({"value": AVRO_PATH})
        encoded = py_to_avro(AVRO_PATH, expected_value)

        result = deserializer.deserialize(encoded, "", MessageField.VALUE)
        self.assertEqual(expected_value, result)

    def test_avro_deserialization_with_magic_byte(self):
        expected_value = {"name": "Pedro Pascal"}
        deserializer = AvroDeserializer({"value": AVRO_PATH, "framing": "confluent"})
        encoded = py_to_avro(AVRO_PATH, expected_value)

        result = deserializer.deserialize(b"\x00\x00\x00\x00\x00" + encoded, "", MessageField.VALUE)

        self.assertEqual(expected_value, result)

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
