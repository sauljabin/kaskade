import json
import os

import struct
import unittest
from typing import Any

from fastavro import schemaless_writer
from fastavro.schema import load_schema
from io import BytesIO
from unittest.mock import patch

from confluent_kafka.serialization import MessageField

from kaskade.deserializers import (
    StringDeserializer,
    IntegerDeserializer,
    DoubleDeserializer,
    FloatDeserializer,
    LongDeserializer,
    BooleanDeserializer,
    DefaultDeserializer,
    JsonDeserializer,
    RegistryDeserializer,
    ProtobufDeserializer,
    AvroDeserializer,
)
from kaskade.utils import file_to_str
from tests import faker
from tests.protobuf.user_pb2 import User


CURRENT_PATH = os.getcwd()
DESCRIPTOR_NAME = "protobuf/user.desc"
DESCRIPTOR_PATH = (
    f"{CURRENT_PATH}/{DESCRIPTOR_NAME}"
    if CURRENT_PATH.endswith("tests")
    else f"{CURRENT_PATH}/tests/{DESCRIPTOR_NAME}"
)

AVRO_SCHEMA_NAME = "avro/user.avsc"
AVRO_PATH = (
    f"{CURRENT_PATH}/{AVRO_SCHEMA_NAME}"
    if CURRENT_PATH.endswith("tests")
    else f"{CURRENT_PATH}/tests/{AVRO_SCHEMA_NAME}"
)


def py_to_avro(expected_value: dict[str, Any]):
    schema = load_schema(AVRO_PATH)
    buffer_writer = BytesIO()
    schemaless_writer(buffer_writer, schema, expected_value)
    encoded = buffer_writer.getvalue()
    return encoded


class TestDeserializer(unittest.TestCase):

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
    def test_registry_deserialization_with_magic_byte(self, mock_sr_client_class):
        expected_value = {"name": "Pedro Pascal"}

        mock_sr_client_class.return_value.get_schema.return_value.schema_str = file_to_str(
            AVRO_PATH
        )

        encoded = py_to_avro(expected_value)

        deserializer = RegistryDeserializer({})

        result = deserializer.deserialize(b"\x00\x00\x00\x00\x00" + encoded, "", MessageField.VALUE)

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
        encoded = py_to_avro(expected_value)

        result = deserializer.deserialize(encoded, "", MessageField.VALUE)
        print(encoded)

        self.assertEqual(expected_value, result)

    def test_avro_deserialization_with_magic_byte(self):
        expected_value = {"name": "Pedro Pascal"}
        deserializer = AvroDeserializer({"value": AVRO_PATH})
        encoded = py_to_avro(expected_value)

        result = deserializer.deserialize(b"\x00\x00\x00\x00\x00" + encoded, "", MessageField.VALUE)

        self.assertEqual(expected_value, result)


if __name__ == "__main__":
    unittest.main()
