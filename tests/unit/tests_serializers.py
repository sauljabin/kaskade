import json
import struct
import tempfile
import unittest
from base64 import b64encode
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from confluent_kafka.schema_registry.error import SchemaRegistryError
from confluent_kafka.serialization import MessageField
from fastavro import parse_schema, schemaless_reader, schemaless_writer
from google.protobuf.descriptor_pb2 import (
    FieldDescriptorProto,
    FileDescriptorProto,
    FileDescriptorSet,
)
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message import Message
from google.protobuf.message_factory import GetMessageClass

from kaskade.apicurio import (
    APICURIO_ARTIFACT_GROUP_ID,
    APICURIO_ARTIFACT_ID,
    APICURIO_ARTIFACT_VERSION,
    APICURIO_AUTO_REGISTER,
    APICURIO_FIND_LATEST,
    ApicurioArtifact,
    ApicurioConfig,
    ApicurioRegistryError,
    ApicurioVersion,
)
from kaskade.configs import (
    APICURIO_OPTION,
    AUTO_REGISTER_SCHEMAS,
    CONFLUENT_OPTION,
    NORMALIZE_SCHEMAS,
    PROTOBUF_MESSAGE,
    USE_LATEST_VERSION,
    USE_SCHEMA_ID,
)
from kaskade.deserializers import (
    BytesEncoding,
    ConfluentRegistryDeserializer,
    Deserialization,
    DeserializerPool,
    ProtobufDeserializer,
)
from kaskade.models import bytes_data
from kaskade.record_export import readable_json
from kaskade.schemas import SchemaError
from kaskade.schemas.json_schema import load_json_schema, validation_error
from kaskade.serializers import (
    SchemaSelection,
    Serialization,
    SerializationError,
    SerializerPool,
    split_registry_config,
)

KEY = MessageField.KEY
VALUE = MessageField.VALUE
APICURIO_URL = "http://registry/apis/registry/v3"


def protobuf_shop_model() -> FileDescriptorProto:
    """A package with a first message, a second one, and a nested message."""
    descriptor = FileDescriptorProto(name="shop.proto", package="shop", syntax="proto3")
    user = descriptor.message_type.add(name="User")
    user.field.add(
        name="name",
        number=1,
        label=FieldDescriptorProto.LABEL_OPTIONAL,
        type=FieldDescriptorProto.TYPE_STRING,
    )
    order = descriptor.message_type.add(name="Order")
    order.field.add(
        name="order_id",
        number=1,
        label=FieldDescriptorProto.LABEL_OPTIONAL,
        type=FieldDescriptorProto.TYPE_INT64,
    )
    line = order.nested_type.add(name="Line")
    line.field.add(
        name="quantity",
        number=1,
        label=FieldDescriptorProto.LABEL_OPTIONAL,
        type=FieldDescriptorProto.TYPE_INT32,
    )
    return descriptor


SHOP_DESCRIPTOR = protobuf_shop_model()


def shop_class(name: str) -> type[Message]:
    pool = DescriptorPool()
    pool.Add(SHOP_DESCRIPTOR)
    return GetMessageClass(pool.FindMessageTypeByName(name))


AVRO_SCHEMA = {
    "type": "record",
    "name": "Payment",
    "namespace": "shop",
    "fields": [
        {"name": "paid_at", "type": {"type": "long", "logicalType": "timestamp-millis"}},
        {"name": "due", "type": {"type": "int", "logicalType": "date"}},
        {
            "name": "amount",
            "type": {"type": "bytes", "logicalType": "decimal", "precision": 8, "scale": 2},
        },
        {"name": "signature", "type": "bytes"},
        {
            "name": "card",
            "type": [
                "null",
                "string",
                {"type": "record", "name": "Card", "fields": [{"name": "last4", "type": "int"}]},
            ],
        },
        {"name": "status", "type": {"type": "enum", "name": "Status", "symbols": ["NEW", "PAID"]}},
        {"name": "tags", "type": {"type": "map", "values": "long"}, "default": {}},
    ],
}
AVRO_VALUE = {
    "paid_at": datetime(2026, 10, 8, 14, 20, 5, 120000, tzinfo=timezone.utc),
    "due": date(2026, 11, 1),
    "amount": Decimal("1234.50"),
    "signature": b"\x00sig\\",
    "card": {"last4": 4242},
    "status": "PAID",
    "tags": {"priority": 1},
}
JSON_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {"name": {"$ref": "defs/name.json"}, "age": {"type": "integer", "minimum": 0}},
    "required": ["name"],
    "additionalProperties": False,
}


def avro_bytes(schema: dict, value: dict) -> bytes:
    output = BytesIO()
    schemaless_writer(output, parse_schema(schema), value)
    return output.getvalue()


def registry_header(schema_id: int) -> bytes:
    return struct.pack(">bI", 0, schema_id)


def apicurio_type_ref(name: str) -> bytes:
    """The type reference the sandbox writes before Apicurio Protobuf payloads."""
    encoded = name.encode()
    message = b"\x0a" + bytes([len(encoded)]) + encoded
    return bytes([len(message)]) + message


class SchemaFiles(unittest.TestCase):
    """Local schema files written to a temporary directory."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def write(self, name: str, content: object) -> str:
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(json.dumps(content), encoding="utf-8")
        return str(path)


class TestPrimitiveSerializers(unittest.TestCase):
    def serialize(self, serialization: Serialization, text: str, **bytes_config: str) -> bytes:
        pool = SerializerPool(bytes_config=bytes_config)
        return pool.get(serialization, VALUE).serialize(text)

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
                    payload, self.serialize(Serialization.BYTES, text, encoding=str(encoding))
                )

    def test_scoped_bytes_encoding_overrides_the_global_one(self):
        pool = SerializerPool(bytes_config={"encoding": "hex", "key.encoding": "escaped"})

        self.assertEqual(b"\x00a", pool.get(Serialization.BYTES, KEY).serialize("\\x00a"))
        self.assertEqual(b"\x00a", pool.get(Serialization.BYTES, VALUE).serialize("0061"))
        self.assertEqual("BYTES · ESCAPED", pool.get(Serialization.BYTES, KEY).label)
        self.assertEqual("BYTES · BASE64", SerializerPool().get(Serialization.BYTES, KEY).label)

    def test_empty_bytes_are_valid(self):
        for encoding in BytesEncoding:
            with self.subTest(encoding=encoding):
                self.assertEqual(
                    b"", self.serialize(Serialization.BYTES, "", encoding=str(encoding))
                )

    def test_invalid_input_is_rejected_without_echoing_content(self):
        cases = (
            (Serialization.BOOLEAN, "yes", {}),
            (Serialization.INTEGER, "2147483648", {}),
            (Serialization.INTEGER, "1.5", {}),
            (Serialization.LONG, "secret", {}),
            (Serialization.FLOAT, "1e40", {}),
            (Serialization.DOUBLE, "secret", {}),
            (Serialization.JSON, "{secret", {}),
            (Serialization.BYTES, "secret!", {"encoding": "base64"}),
            (Serialization.BYTES, "secret", {"encoding": "hex"}),
            (Serialization.BYTES, "[256]", {"encoding": "byte-array"}),
            (Serialization.BYTES, "[true]", {"encoding": "byte-array"}),
            (Serialization.BYTES, "secret\\q", {"encoding": "escaped"}),
            (Serialization.BYTES, "ñ", {"encoding": "escaped"}),
        )
        for serialization, text, bytes_config in cases:
            with (
                self.subTest(serialization=serialization, text=text),
                self.assertRaises(SerializationError) as raised,
            ):
                self.serialize(serialization, text, **bytes_config)
            self.assertNotIn("secret", str(raised.exception))

    def test_float_uses_big_endian_ieee_754(self):
        self.assertEqual(struct.pack(">f", 2.5), self.serialize(Serialization.FLOAT, "2.5"))
        self.assertEqual(struct.pack(">d", 2.5), self.serialize(Serialization.DOUBLE, "2.5"))

    def test_draft_text_formats_source_content_for_the_editor(self):
        pool = SerializerPool()

        self.assertEqual("order-1", pool.get(Serialization.STRING, KEY).draft_text("order-1"))
        self.assertEqual("42", pool.get(Serialization.INTEGER, KEY).draft_text(42))
        self.assertEqual("true", pool.get(Serialization.BOOLEAN, KEY).draft_text(True))
        self.assertEqual('"text"', pool.get(Serialization.JSON, KEY).draft_text("text"))
        self.assertEqual('{\n  "a": 1\n}', pool.get(Serialization.JSON, KEY).draft_text({"a": 1}))

    def test_json_input_is_marked_for_highlighting(self):
        pool = SerializerPool(bytes_config={"key.encoding": "byte-array"})
        highlighted = {
            Serialization.JSON,
            Serialization.BOOLEAN,
            Serialization.INTEGER,
            Serialization.LONG,
            Serialization.FLOAT,
            Serialization.DOUBLE,
        }
        for serialization in highlighted | {Serialization.STRING, Serialization.BYTES}:
            with self.subTest(serialization=serialization):
                self.assertEqual(
                    serialization in highlighted,
                    pool.get(serialization, VALUE).edits_json,
                )
        self.assertTrue(pool.get(Serialization.BYTES, KEY).edits_json)


class TestJsonSchemaSerializer(SchemaFiles):
    def setUp(self) -> None:
        super().setUp()
        self.write("defs/name.json", {"type": "string", "minLength": 2})
        self.schema_path = self.write("user.json", JSON_SCHEMA)
        self.serializer = SerializerPool(json_config={"value": self.schema_path}).get(
            Serialization.JSON, VALUE
        )

    def test_validates_against_the_schema_and_its_local_references(self):
        self.assertEqual(
            b'{"name":"Ada","age":3}', self.serializer.serialize('{"name":"Ada","age":3}')
        )
        self.assertEqual("JSON · user.json", self.serializer.label)
        self.assertEqual(
            "JSON",
            SerializerPool(json_config={"value": self.schema_path})
            .get(Serialization.JSON, KEY)
            .label,
        )

    def test_errors_name_the_path_and_rule_but_never_the_content(self):
        cases = {
            '{"age": 3}': "$ missing required property name",
            '{"name": "A"}': "$.name fails minLength 2",
            '{"name": "Ada", "age": -7}': "$.age fails minimum 0",
            '{"name": "Ada", "secret": "hidden"}': "$ fails additionalProperties false",
            '{"name": ["secret"]}': "$.name expected type string",
        }
        for text, expected in cases.items():
            with self.subTest(text=text), self.assertRaises(SerializationError) as raised:
                self.serializer.serialize(text)
            self.assertEqual(f"JSON Schema validation failed: {expected}", str(raised.exception))
            self.assertNotIn("hidden", str(raised.exception))
            self.assertNotIn("-7", str(raised.exception))

    def test_remote_and_escaping_references_are_never_loaded(self):
        remote = self.write("remote.json", {"$ref": "https://example.com/name.json"})
        escaping = self.write("escaping.json", {"$ref": "../name.json"})
        missing = self.write("missing.json", {"$ref": "nowhere.json"})

        with self.assertRaisesRegex(SchemaError, "must stay next to the schema"):
            load_json_schema(escaping)
        with self.assertRaisesRegex(SchemaError, "Unable to read"):
            load_json_schema(missing)
        validator = load_json_schema(remote)
        with patch("httpx.get") as http_get, self.assertRaises(SchemaError):
            validation_error(validator, "Ada")
        http_get.assert_not_called()

    def test_invalid_schemas_are_rejected(self):
        invalid = self.write("invalid.json", {"type": "no-such-type"})
        (self.directory / "broken.json").write_text("{", encoding="utf-8")

        with self.assertRaisesRegex(SchemaError, "Invalid JSON Schema"):
            load_json_schema(invalid)
        with self.assertRaisesRegex(SchemaError, "Invalid JSON in"):
            load_json_schema(self.directory / "broken.json")


class TestLocalAvroAndProtobuf(SchemaFiles):
    def test_avro_round_trips_the_consumer_rendering(self):
        schema_path = self.write("payment.avsc", AVRO_SCHEMA)
        serializer = SerializerPool(avro_config={"value": schema_path}).get(
            Serialization.AVRO, VALUE
        )
        consumer_json = readable_json(AVRO_VALUE)

        data = serializer.serialize(consumer_json)

        self.assertEqual(avro_bytes(AVRO_SCHEMA, AVRO_VALUE), data)
        decoded = schemaless_reader(BytesIO(data), parse_schema(AVRO_SCHEMA), None)
        self.assertEqual(AVRO_VALUE, decoded)
        self.assertEqual("AVRO · payment.avsc", serializer.label)
        self.assertTrue(serializer.edits_json)

    def test_avro_accepts_iso_timestamps_and_union_branches(self):
        schema_path = self.write("payment.avsc", AVRO_SCHEMA)
        serializer = SerializerPool(avro_config={"key": schema_path}).get(Serialization.AVRO, KEY)
        content = {
            "paid_at": "2026-10-08T14:20:05.120Z",
            "due": "2026-11-01",
            "amount": 1234.5,
            "signature": "b''",
            "card": "visa",
            "status": "NEW",
        }

        data = serializer.serialize(json.dumps(content))

        decoded = schemaless_reader(BytesIO(data), parse_schema(AVRO_SCHEMA), None)
        self.assertEqual(AVRO_VALUE["paid_at"], decoded["paid_at"])
        self.assertEqual(Decimal("1234.50"), decoded["amount"])
        self.assertEqual("visa", decoded["card"])
        self.assertEqual({}, decoded["tags"])

    def test_avro_errors_name_the_field_but_never_the_content(self):
        schema_path = self.write("payment.avsc", AVRO_SCHEMA)
        serializer = SerializerPool(avro_config={"value": schema_path}).get(
            Serialization.AVRO, VALUE
        )
        valid = json.loads(readable_json(AVRO_VALUE))
        cases = (
            (valid | {"status": "secret"}, "at shop.Payment.status: expected enum shop.Status"),
            (valid | {"paid_at": "secret"}, "at shop.Payment.paid_at: expected long"),
            (valid | {"card": {"last4": "secret"}}, "at shop.Card.last4: expected int"),
            (["secret"], "at the root: expected record shop.Payment"),
        )
        for content, expected in cases:
            with self.subTest(expected=expected), self.assertRaises(SerializationError) as raised:
                serializer.serialize(json.dumps(content))
            self.assertIn(expected, str(raised.exception))
            self.assertNotIn("secret", str(raised.exception))

    def test_protobuf_round_trips_the_consumer_rendering(self):
        descriptor_path = self.write(
            "shop.desc", FileDescriptorSet(file=[SHOP_DESCRIPTOR]).SerializeToString()
        )
        config = {"descriptor": descriptor_path, "value": "shop.Order"}
        serializer = SerializerPool(protobuf_config=config).get(Serialization.PROTOBUF, VALUE)
        consumer = ProtobufDeserializer(config)

        data = serializer.serialize('{"orderId": "9007199254740993"}')

        self.assertEqual(
            shop_class("shop.Order")(order_id=9007199254740993).SerializeToString(), data
        )
        decoded = consumer.deserialize(data, "orders", VALUE)
        self.assertEqual(data, serializer.serialize(json.dumps(decoded)))
        self.assertEqual("PROTOBUF · shop.Order", serializer.label)

    def test_protobuf_errors_never_echo_content(self):
        descriptor_path = self.write(
            "shop.desc", FileDescriptorSet(file=[SHOP_DESCRIPTOR]).SerializeToString()
        )
        config = {"descriptor": descriptor_path, "value": "shop.Order"}
        serializer = SerializerPool(protobuf_config=config).get(Serialization.PROTOBUF, VALUE)
        cases = (
            ('{"orderId": "secret"}', "invalid value for orderId"),
            ('{"secret": 1}', "unknown field"),
            ('["secret"]', "Expected a JSON object"),
        )
        for text, expected in cases:
            with self.subTest(text=text), self.assertRaises(SerializationError) as raised:
                serializer.serialize(text)
            self.assertIn(expected, str(raised.exception))
            self.assertNotIn("secret", str(raised.exception))

    def test_unusable_schema_files_raise_schema_errors(self):
        broken = self.directory / "broken.avsc"
        broken.write_text("{", encoding="utf-8")
        descriptor_path = self.write(
            "shop.desc", FileDescriptorSet(file=[SHOP_DESCRIPTOR]).SerializeToString()
        )

        with self.assertRaisesRegex(SchemaError, "Invalid Avro schema"):
            SerializerPool(avro_config={"value": str(broken)}).get(Serialization.AVRO, VALUE)
        with self.assertRaisesRegex(SchemaError, "shop.Missing isn't in"):
            SerializerPool(
                protobuf_config={"descriptor": descriptor_path, "value": "shop.Missing"}
            ).get(Serialization.PROTOBUF, VALUE)


class TestSchemaSelection(unittest.TestCase):
    def test_splits_selection_properties_from_client_properties(self):
        client, selection = split_registry_config(
            {
                "url": "http://registry",
                USE_SCHEMA_ID: "4",
                f"key.{PROTOBUF_MESSAGE}": "shop.Order",
                APICURIO_ARTIFACT_ID: "orders",
            }
        )

        self.assertEqual({"url": "http://registry"}, client)
        self.assertEqual(
            {
                USE_SCHEMA_ID: "4",
                f"key.{PROTOBUF_MESSAGE}": "shop.Order",
                APICURIO_ARTIFACT_ID: "orders",
            },
            selection,
        )

    def test_scoped_properties_override_global_ones(self):
        config = {USE_SCHEMA_ID: "4", f"value.{USE_SCHEMA_ID}": "9", USE_LATEST_VERSION: "TRUE"}

        self.assertEqual(4, SchemaSelection.from_config(config, CONFLUENT_OPTION, KEY).schema_id)
        self.assertEqual(9, SchemaSelection.from_config(config, CONFLUENT_OPTION, VALUE).schema_id)
        apicurio = SchemaSelection.from_config(
            {APICURIO_ARTIFACT_ID: "shared", APICURIO_FIND_LATEST: "true"}, APICURIO_OPTION, KEY
        )
        self.assertEqual(SchemaSelection(artifact="shared"), apicurio)

    def test_rejects_conflicting_and_unsupported_lookups(self):
        cases = (
            (CONFLUENT_OPTION, {USE_LATEST_VERSION: "false"}, "needs auto.register.schemas=true"),
            (CONFLUENT_OPTION, {USE_LATEST_VERSION: "maybe"}, "must be true or false"),
            (CONFLUENT_OPTION, {AUTO_REGISTER_SCHEMAS: "yes"}, "must be true or false"),
            (
                CONFLUENT_OPTION,
                {AUTO_REGISTER_SCHEMAS: "true", USE_LATEST_VERSION: "true"},
                "can't be combined with use.latest.version",
            ),
            (
                CONFLUENT_OPTION,
                {f"value.{AUTO_REGISTER_SCHEMAS}": "True", USE_SCHEMA_ID: "4"},
                "can't be combined with use.schema.id",
            ),
            (CONFLUENT_OPTION, {USE_SCHEMA_ID: "0"}, "must be a positive integer"),
            (CONFLUENT_OPTION, {USE_SCHEMA_ID: "one"}, "must be a positive integer"),
            (CONFLUENT_OPTION, {APICURIO_ARTIFACT_ID: "orders"}, "requires provider=apicurio"),
            (APICURIO_OPTION, {APICURIO_FIND_LATEST: "false"}, "needs apicurio.registry.artifact"),
            (
                APICURIO_OPTION,
                {APICURIO_AUTO_REGISTER: "true", APICURIO_FIND_LATEST: "true"},
                "can't be combined with apicurio.registry.find-latest",
            ),
            (
                APICURIO_OPTION,
                {APICURIO_AUTO_REGISTER: "true", APICURIO_ARTIFACT_VERSION: "2"},
                "can't be combined with apicurio.registry.artifact.version",
            ),
            (APICURIO_OPTION, {USE_SCHEMA_ID: "4"}, "requires provider=confluent"),
            (APICURIO_OPTION, {NORMALIZE_SCHEMAS: "true"}, "requires provider=confluent"),
            (APICURIO_OPTION, {APICURIO_ARTIFACT_GROUP_ID: ""}, "must not be empty"),
        )
        for provider, config, message in cases:
            with self.subTest(config=config), self.assertRaisesRegex(ValueError, message):
                SchemaSelection.from_config(config, provider, VALUE)

    def test_accepts_registration_and_pinned_versions(self):
        confluent = SchemaSelection.from_config(
            {
                AUTO_REGISTER_SCHEMAS: "true",
                USE_LATEST_VERSION: "false",
                f"value.{NORMALIZE_SCHEMAS}": "true",
            },
            CONFLUENT_OPTION,
            VALUE,
        )
        self.assertEqual(SchemaSelection(auto_register=True, normalize=True), confluent)
        self.assertFalse(
            SchemaSelection.from_config(
                {AUTO_REGISTER_SCHEMAS: "false"}, CONFLUENT_OPTION, KEY
            ).auto_register
        )
        apicurio = SchemaSelection.from_config(
            {APICURIO_AUTO_REGISTER: "true", APICURIO_FIND_LATEST: "false"}, APICURIO_OPTION, KEY
        )
        self.assertEqual(SchemaSelection(auto_register=True), apicurio)
        pinned = SchemaSelection.from_config(
            {
                APICURIO_FIND_LATEST: "false",
                APICURIO_ARTIFACT_VERSION: "2",
                APICURIO_ARTIFACT_GROUP_ID: "payments",
            },
            APICURIO_OPTION,
            VALUE,
        )
        self.assertEqual(SchemaSelection(group="payments", version="2"), pinned)


class TestConfluentRegistrySerializer(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch("kaskade.serializers.registry.SchemaRegistryClient")
        self.addCleanup(patcher.stop)
        self.client = patcher.start().return_value
        self.client.get_latest_version.return_value = SimpleNamespace(schema_id=7, version=3)

    def serializer(self, field: MessageField = VALUE, **selection: str):
        pool = SerializerPool("orders", registry_config={"url": "http://registry", **selection})
        serializer = pool.get(Serialization.REGISTRY, field)
        serializer.resolve()
        return serializer

    def schema(self, schema_str: str, schema_type: str = "AVRO") -> SimpleNamespace:
        return SimpleNamespace(schema_str=schema_str, schema_type=schema_type, references=[])

    def test_avro_uses_the_latest_topic_name_strategy_version(self):
        self.client.get_schema.return_value = self.schema(json.dumps(AVRO_SCHEMA))
        serializer = self.serializer()

        data = serializer.serialize(readable_json(AVRO_VALUE))

        self.client.get_latest_version.assert_called_once_with("orders-value")
        self.client.get_schema.assert_called_once_with(7)
        self.assertEqual(registry_header(7) + avro_bytes(AVRO_SCHEMA, AVRO_VALUE), data)
        self.assertEqual("REGISTRY · AVRO", serializer.label)
        summary = serializer.schema
        self.assertEqual(("orders-value", "3", 7, "AVRO"), tuple(vars(summary).values()))

    def test_avro_references_are_parsed_first(self):
        card = {
            "type": "record",
            "name": "Card",
            "namespace": "shop",
            "fields": [{"name": "last4", "type": "int"}],
        }
        payment = {
            "type": "record",
            "name": "Payment",
            "namespace": "shop",
            "fields": [{"name": "card", "type": "shop.Card"}],
        }
        reference = SimpleNamespace(name="shop.Card", subject="card", version=1)
        self.client.get_schema.return_value = SimpleNamespace(
            schema_str=json.dumps(payment), schema_type="AVRO", references=[reference]
        )
        self.client.get_version.return_value = SimpleNamespace(schema=self.schema(json.dumps(card)))

        data = self.serializer().serialize('{"card": {"last4": 4242}}')

        self.client.get_version.assert_called_once_with("card", 1, deleted=True, fmt=None)
        self.assertEqual(registry_header(7) + avro_bytes(card, {"last4": 4242}), data)

    def test_json_schema_is_validated_and_framed(self):
        self.client.get_schema.return_value = self.schema(
            json.dumps({"type": "object", "required": ["name"]}), "JSON"
        )
        serializer = self.serializer(KEY)

        self.assertEqual(
            registry_header(7) + b'{"name":"Ada"}', serializer.serialize('{"name": "Ada"}')
        )
        self.client.get_latest_version.assert_called_once_with("orders-key")
        with self.assertRaisesRegex(SerializationError, "missing required property name"):
            serializer.serialize("{}")

    def test_protobuf_writes_message_indexes_the_consumer_reads(self):
        serialized = SimpleNamespace(
            schema_str=b64encode(SHOP_DESCRIPTOR.SerializeToString()).decode(),
            schema_type="PROTOBUF",
            references=[],
        )
        self.client.get_schema.return_value = serialized
        consumer_client = MagicMock()
        consumer_client.get_schema.return_value = serialized
        cases = (
            ({}, '{"name": "Ada"}', b"\x00"),
            ({PROTOBUF_MESSAGE: "Order"}, '{"orderId": "5"}', b"\x02\x02"),
            ({f"value.{PROTOBUF_MESSAGE}": "shop.Order.Line"}, '{"quantity": 2}', b"\x04\x02\x00"),
        )
        for selection, text, indexes in cases:
            with self.subTest(selection=selection):
                data = self.serializer(**selection).serialize(text)
                self.assertEqual(registry_header(7) + indexes, data[: 5 + len(indexes)])
                with patch(
                    "kaskade.deserializers.confluent.SchemaRegistryClient",
                    return_value=consumer_client,
                ):
                    decoded = ConfluentRegistryDeserializer({}).deserialize(data, "orders", VALUE)
                self.assertEqual(json.loads(text), decoded)

    def test_use_schema_id_skips_the_latest_version(self):
        self.client.get_schema.return_value = self.schema(json.dumps(AVRO_SCHEMA))
        self.client.get_schema_versions.return_value = [
            SimpleNamespace(subject="other", version=1),
            SimpleNamespace(subject="orders-value", version=5),
        ]

        serializer = self.serializer(**{USE_SCHEMA_ID: "12"})

        self.client.get_latest_version.assert_not_called()
        self.assertEqual("5", serializer.schema.version)
        self.assertEqual(12, serializer.schema.id)
        self.assertEqual(registry_header(12), serializer.serialize(readable_json(AVRO_VALUE))[:5])

    def test_lookup_failures_are_reported_until_a_retry_succeeds(self):
        self.client.get_latest_version.side_effect = [
            SchemaRegistryError(404, 40401, "Subject 'orders-value' not found."),
            SimpleNamespace(schema_id=7, version=3),
        ]
        self.client.get_schema.return_value = self.schema(json.dumps(AVRO_SCHEMA))
        pool = SerializerPool("orders", registry_config={"url": "http://registry"})
        serializer = pool.get(Serialization.REGISTRY, VALUE)

        with self.assertRaisesRegex(SerializationError, "Looking up the schema"):
            serializer.serialize("{}")
        self.assertTrue(serializer.needs_schema)
        with self.assertLogs("kaskade", level="WARNING") as logs:
            serializer.resolve()
        with self.assertRaisesRegex(SerializationError, "Subject 'orders-value' not found"):
            serializer.serialize('{"secret": 1}')
        self.assertNotIn("secret", "\n".join(logs.output))

        serializer.resolve()
        self.assertFalse(serializer.needs_schema)
        self.assertEqual("REGISTRY · AVRO", serializer.label)

    def test_the_pool_shares_and_closes_one_client(self):
        pool = SerializerPool(
            "orders", registry_config={"provider": "confluent", "url": "http://registry"}
        )
        pool.get(Serialization.REGISTRY, KEY)
        pool.get(Serialization.REGISTRY, VALUE)
        pool.close()

        self.client.close.assert_called_once_with()


class TestApicurioRegistrySerializer(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch("kaskade.serializers.registry.ApicurioClient")
        self.addCleanup(patcher.stop)
        self.client_class = patcher.start()
        self.client = self.client_class.return_value
        self.client.config.use_id = "contentId"
        self.client.get_version.return_value = ApicurioVersion(
            "default", "orders-value", "2", 31, 12
        )

    def serializer(self, field: MessageField = VALUE, **selection: str):
        config = {"provider": APICURIO_OPTION, "apicurio.registry.url": APICURIO_URL}
        pool = SerializerPool(
            "orders",
            registry_config=config | selection,
            apicurio_config=ApicurioConfig.from_dict(config),
        )
        serializer = pool.get(Serialization.REGISTRY, field)
        serializer.resolve()
        return serializer

    def artifact(self, content: str, artifact_type: str) -> ApicurioArtifact:
        return ApicurioArtifact(12, "CONTENT_ID", content, artifact_type, ())

    def test_frames_like_the_sandbox_apicurio_records(self):
        protobuf_source = 'syntax = "proto3"; message User { string name = 1; }'
        cases = (
            (
                "AVRO",
                json.dumps(AVRO_SCHEMA),
                readable_json(AVRO_VALUE),
                avro_bytes(AVRO_SCHEMA, AVRO_VALUE),
            ),
            ("JSON", json.dumps({"type": "object"}), '{"name": "Ada"}', b'{"name":"Ada"}'),
            (
                "PROTOBUF",
                protobuf_source,
                '{"name": "Ada"}',
                apicurio_type_ref("User") + b"\x0a\x03Ada",
            ),
        )
        for artifact_type, content, text, payload in cases:
            with self.subTest(artifact_type=artifact_type):
                self.client.get_artifact.return_value = self.artifact(content, artifact_type)
                serializer = self.serializer()

                self.assertEqual(registry_header(12) + payload, serializer.serialize(text))
                self.assertEqual(
                    ("orders-value", "2", 12, artifact_type),
                    tuple(vars(serializer.schema).values()),
                )
        self.client.get_version.assert_called_with("default", "orders-value", "branch=latest")
        self.client.get_artifact.assert_called_with(12)

    def test_selection_properties_choose_group_artifact_version_and_message(self):
        source = (
            'syntax = "proto3"; package shop; message User { string name = 1; } '
            "message Order { message Line { int32 quantity = 1; } }"
        )
        self.client.config.use_id = "globalId"
        self.client.get_artifact.return_value = self.artifact(source, "PROTOBUF")

        serializer = self.serializer(
            KEY,
            **{
                APICURIO_ARTIFACT_GROUP_ID: "payments",
                APICURIO_ARTIFACT_ID: "shared",
                f"key.{APICURIO_ARTIFACT_VERSION}": "2",
                PROTOBUF_MESSAGE: "Order.Line",
            },
        )

        self.client.get_version.assert_called_once_with("payments", "shared", "2")
        self.client.get_artifact.assert_called_once_with(31)
        data = serializer.serialize('{"quantity": 2}')
        self.assertEqual(registry_header(31) + apicurio_type_ref("Order.Line") + b"\x08\x02", data)
        self.assertEqual("payments/shared", serializer.schema.name)

    def test_a_missing_artifact_is_reported_clearly(self):
        response = httpx.Response(404, request=httpx.Request("GET", APICURIO_URL))
        error = ApicurioRegistryError("Apicurio request failed")
        error.__cause__ = httpx.HTTPStatusError("404", request=response.request, response=response)
        self.client.get_version.side_effect = error

        with self.assertLogs("kaskade", level="WARNING"):
            serializer = self.serializer()

        with self.assertRaisesRegex(
            SerializationError, "Apicurio artifact orders-value has no such version"
        ):
            serializer.serialize("{}")


if __name__ == "__main__":
    unittest.main()
