import json
import os
import struct
import unittest
from io import BytesIO
from unittest.mock import patch

import avro
from avro.io import DatumWriter, BinaryEncoder

from kaskade.deserializers import (
    StringDeserializer,
    IntegerDeserializer,
    DoubleDeserializer,
    FloatDeserializer,
    LongDeserializer,
    BooleanDeserializer,
    DefaultDeserializer,
    JsonDeserializer,
    AvroDeserializer,
)
from tests import faker


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
    def test_avro_deserialization_with_magic_byte(self, mock_sr_client_class):
        schema_source = """
        {
            "namespace": "example.avro",
             "type": "record",
             "name": "User",
             "fields": [
                 {"name": "name", "type": "string"}
             ]
        }
        """
        expected_value = {"name": "Pedro Pascal"}

        mock_sr_client_class.return_value.get_schema.return_value.schema_str = schema_source

        schema = avro.schema.parse(schema_source)
        buffer_writer = BytesIO()
        buffer_encoder = BinaryEncoder(buffer_writer)
        writer = DatumWriter(schema)
        writer.write(expected_value, buffer_encoder)

        deserializer = AvroDeserializer({})

        result = deserializer.deserialize(b"\x00\x00\x00\x00\x00" + buffer_writer.getvalue())

        self.assertEqual(expected_value, result)
