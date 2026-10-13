import unittest
from struct import pack

from kaskade.deserializers import BytesEncoding, Deserialization, DeserializerPool
from kaskade.models import bytes_data
from kaskade.serializers import Serialization, SerializationError, SerializerPool


class TestSerializers(unittest.TestCase):
    def setUp(self) -> None:
        self.pool = SerializerPool()

    def serialize(self, serialization: Serialization, text: str, **kwargs) -> bytes:
        return self.pool.get(serialization, **kwargs).serialize(text)

    def test_primitives_match_the_deserializers(self):
        deserializers = DeserializerPool()
        cases = (
            (Serialization.STRING, "pedido ñ", Deserialization.STRING, "pedido ñ"),
            (Serialization.STRING, "", Deserialization.STRING, ""),
            (Serialization.BOOLEAN, " TRUE ", Deserialization.BOOLEAN, True),
            (Serialization.INTEGER, "-2147483648", Deserialization.INTEGER, -(2**31)),
            (Serialization.LONG, "9223372036854775807", Deserialization.LONG, 2**63 - 1),
            (Serialization.FLOAT, "1.5", Deserialization.FLOAT, 1.5),
            (Serialization.DOUBLE, "-0.25", Deserialization.DOUBLE, -0.25),
        )
        for serialization, text, deserialization, expected in cases:
            with self.subTest(serialization=serialization, text=text):
                data = self.serialize(serialization, text)
                self.assertEqual(expected, deserializers.get(deserialization).deserialize(data))

    def test_json_is_validated_and_sent_compact_in_key_order(self):
        data = self.serialize(Serialization.JSON, '{\n  "b": 1,\n  "a": "ñ"\n}')

        self.assertEqual('{"b":1,"a":"ñ"}'.encode(), data)
        self.assertEqual(b'""', self.serialize(Serialization.JSON, '""'))

    def test_bytes_round_trip_every_consumer_encoding(self):
        payload = bytes(range(256))
        for encoding in BytesEncoding:
            with self.subTest(encoding=encoding):
                encoded = bytes_data(payload, encoding)
                text = encoded if isinstance(encoded, str) else str(encoded)
                self.assertEqual(
                    payload, self.serialize(Serialization.BYTES, text, encoding=encoding)
                )

    def test_empty_bytes_are_valid(self):
        for encoding in BytesEncoding:
            with self.subTest(encoding=encoding):
                self.assertEqual(b"", self.serialize(Serialization.BYTES, "", encoding=encoding))

    def test_invalid_input_is_rejected_without_echoing_content(self):
        cases = (
            (Serialization.BOOLEAN, "yes", {}),
            (Serialization.INTEGER, "2147483648", {}),
            (Serialization.INTEGER, "1.5", {}),
            (Serialization.LONG, "secret", {}),
            (Serialization.FLOAT, "1e40", {}),
            (Serialization.DOUBLE, "secret", {}),
            (Serialization.JSON, "{secret", {}),
            (Serialization.BYTES, "secret!", {"encoding": BytesEncoding.BASE64}),
            (Serialization.BYTES, "secret", {"encoding": BytesEncoding.HEX}),
            (Serialization.BYTES, "[256]", {"encoding": BytesEncoding.BYTE_ARRAY}),
            (Serialization.BYTES, "[true]", {"encoding": BytesEncoding.BYTE_ARRAY}),
            (Serialization.BYTES, "secret\\q", {"encoding": BytesEncoding.ESCAPED}),
            (Serialization.BYTES, "ñ", {"encoding": BytesEncoding.ESCAPED}),
        )
        for serialization, text, kwargs in cases:
            with (
                self.subTest(serialization=serialization, text=text),
                self.assertRaises(SerializationError) as raised,
            ):
                self.serialize(serialization, text, **kwargs)
            self.assertNotIn("secret", str(raised.exception))

    def test_float_uses_big_endian_ieee_754(self):
        self.assertEqual(pack(">f", 2.5), self.serialize(Serialization.FLOAT, "2.5"))
        self.assertEqual(pack(">d", 2.5), self.serialize(Serialization.DOUBLE, "2.5"))

    def test_draft_text_formats_source_content_for_the_editor(self):
        self.assertEqual("order-1", self.pool.get(Serialization.STRING).draft_text("order-1"))
        self.assertEqual("42", self.pool.get(Serialization.INTEGER).draft_text(42))
        self.assertEqual("true", self.pool.get(Serialization.BOOLEAN).draft_text(True))
        self.assertEqual('"text"', self.pool.get(Serialization.JSON).draft_text("text"))
        self.assertEqual('{\n  "a": 1\n}', self.pool.get(Serialization.JSON).draft_text({"a": 1}))


if __name__ == "__main__":
    unittest.main()
