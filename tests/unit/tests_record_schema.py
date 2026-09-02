import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from confluent_kafka.serialization import MessageField
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from kaskade.deserializers import (
    BytesEncoding,
    Deserialization,
    DeserializationError,
    DeserializationResult,
    Deserializer,
    RegistrySchema,
    StringDeserializer,
)
from kaskade.models import Header, Record

PROJECT_PATH = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_PATH / "schemas" / "consumer-record.schema.json"


class MetadataDeserializer(Deserializer):
    def deserialize(
        self,
        data: bytes,
        topic: str | None = None,
        context: MessageField = MessageField.NONE,
    ) -> object:
        return {"status": "paid"}

    def deserialize_with_metadata(
        self,
        data: bytes,
        topic: str | None = None,
        context: MessageField = MessageField.NONE,
    ) -> DeserializationResult:
        return DeserializationResult(
            self.deserialize(data, topic, context),
            RegistrySchema(27, "orders-value", 5, "JSON"),
        )


class TestConsumerRecordSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def assert_valid(self, record: Record) -> None:
        self.validator.validate(record.dict())

    def test_schema_is_versionless_draft_2020_12(self) -> None:
        self.assertEqual(
            "https://json-schema.org/draft/2020-12/schema",
            self.schema["$schema"],
        )
        self.assertNotIn("contract_version", self.schema["properties"])

    def test_all_byte_encodings_validate_for_content_errors_and_headers(self) -> None:
        for bytes_encoding in BytesEncoding:
            key_deserializer = MagicMock()
            key_deserializer.deserialize.side_effect = DeserializationError("malformed key")
            record = Record(
                topic="orders",
                partition=0,
                offset=42,
                key=b"\xff",
                value=b"Hello world",
                headers=[
                    Header("source", b"storefront", StringDeserializer(), bytes_encoding),
                    Header("binary", b"\xff", StringDeserializer(), bytes_encoding),
                    Header("nullable", None, StringDeserializer(), bytes_encoding),
                ],
                key_deserialization=Deserialization.JSON,
                value_deserialization=Deserialization.BYTES,
                key_deserializer=key_deserializer,
                key_bytes_encoding=bytes_encoding,
                value_bytes_encoding=bytes_encoding,
                fallback_bytes_encoding=bytes_encoding,
            )

            with self.subTest(bytes_encoding=bytes_encoding):
                self.assert_valid(record)

    def test_registry_metadata_and_every_null_deserializer_validate(self) -> None:
        registry_record = Record(
            topic="orders",
            partition=0,
            offset=43,
            timestamp=datetime(2026, 9, 1, 19, 13, 18, 27_000, tzinfo=timezone.utc),
            value=b"payload",
            value_deserialization=Deserialization.REGISTRY,
            value_deserializer=MetadataDeserializer(),
        )
        self.assert_valid(registry_record)

        for deserialization in Deserialization:
            with self.subTest(deserialization=deserialization):
                self.assert_valid(
                    Record(
                        topic="orders",
                        partition=0,
                        offset=44,
                        key_deserialization=deserialization,
                        value_deserialization=deserialization,
                    )
                )

    def test_schema_rejects_inconsistent_contracts(self) -> None:
        valid = Record(
            topic="orders",
            partition=0,
            offset=42,
            key=b"Hello world",
            key_bytes_encoding=BytesEncoding.BASE64,
        ).dict()

        old_wrapper = deepcopy(valid)
        old_wrapper["key"]["content"] = {
            "encoding": "BASE64",
            "data": "SGVsbG8gd29ybGQ=",
        }
        with self.assertRaises(ValidationError):
            self.validator.validate(old_wrapper)

        nullable_schema = deepcopy(valid)
        nullable_schema["value"]["deserializer"]["schema"] = None
        with self.assertRaises(ValidationError):
            self.validator.validate(nullable_schema)

        mismatched_encoding = deepcopy(valid)
        mismatched_encoding["key"]["deserializer"]["encoding"] = "BYTE_ARRAY"
        with self.assertRaises(ValidationError):
            self.validator.validate(mismatched_encoding)

        contract_version = deepcopy(valid)
        contract_version["contract_version"] = 1
        with self.assertRaises(ValidationError):
            self.validator.validate(contract_version)

        wrapped_header = Record(
            topic="orders",
            partition=0,
            offset=42,
            headers=[Header("source", b"storefront", StringDeserializer())],
        ).dict()
        wrapped_header["headers"][0]["value"] = {
            "content": "storefront",
            "deserializer": {"type": "STRING"},
        }
        with self.assertRaises(ValidationError):
            self.validator.validate(wrapped_header)

        error_deserializer = MagicMock()
        error_deserializer.deserialize.side_effect = DeserializationError("malformed key")
        old_fallback = Record(
            topic="orders",
            partition=0,
            offset=42,
            key=b"\xff",
            key_deserialization=Deserialization.JSON,
            key_deserializer=error_deserializer,
        ).dict()
        error = old_fallback["key"]["error"]
        error["fallback"] = error["fallback"]["type"]
        with self.assertRaises(ValidationError):
            self.validator.validate(old_fallback)
