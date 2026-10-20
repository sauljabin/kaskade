import json
import struct
import tempfile
import unittest
from base64 import b64decode
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import httpx
from click import BadParameter
from confluent_kafka.schema_registry import Schema, SchemaReference
from confluent_kafka.schema_registry.error import SchemaRegistryError
from confluent_kafka.serialization import MessageField
from google.protobuf.descriptor_pb2 import FileDescriptorProto, FileDescriptorSet

from kaskade.apicurio import (
    ApicurioArtifact,
    ApicurioClient,
    ApicurioConfig,
    ApicurioReference,
    ApicurioRegistryError,
    ApicurioVersion,
)
from kaskade.cli.validation import normalize_serializer_options
from kaskade.configs import SchemaType
from kaskade.deserializers import ProtobufDeserializer
from kaskade.schemas import SchemaError
from kaskade.schemas.protobuf import compile_proto_file
from kaskade.schemas.registration import (
    DocumentReference,
    SchemaDocument,
    avro_document,
    json_document,
    protobuf_document,
)
from kaskade.serializers import Serialization, SerializationError, SerializerPool

VALUE = MessageField.VALUE
APICURIO_URL = "http://registry/apis/registry/v3"
APICURIO_CONFIG = {"provider": "apicurio", "apicurio.registry.url": APICURIO_URL}
CARD = {
    "type": "record",
    "name": "Card",
    "namespace": "shop",
    "fields": [{"name": "last4", "type": "int"}],
}
PAYMENT = {
    "type": "record",
    "name": "Payment",
    "namespace": "shop",
    "fields": [{"name": "card", "type": "Card"}, {"name": "backup", "type": ["null", "shop.Card"]}],
}
ADDRESS_PROTO = 'syntax = "proto3";\npackage shop;\nmessage Address { string city = 1; }\n'
USER_PROTO = (
    'syntax = "proto3";\npackage shop;\nimport "common/address.proto";\n'
    'import "google/protobuf/timestamp.proto";\n'
    "message User {\n  string name = 1;\n  Address address = 2;\n"
    "  google.protobuf.Timestamp created = 3;\n}\n"
)


def header(schema_id: int) -> bytes:
    return struct.pack(">bI", 0, schema_id)


class SchemaFiles(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def write(self, name: str, content: object) -> str:
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        text = content if isinstance(content, str) else json.dumps(content)
        path.write_text(text, encoding="utf-8")
        return str(path)

    def proto_files(self) -> str:
        self.write("common/address.proto", ADDRESS_PROTO)
        return self.write("user.proto", USER_PROTO)


class TestSchemaDocuments(SchemaFiles):
    def test_avro_named_types_come_from_files_next_to_the_schema(self):
        self.write("shop.Card.avsc", CARD)
        path = self.write("payment.avsc", PAYMENT)

        document = avro_document(path)

        card = SchemaDocument(SchemaType.AVRO, json.dumps(CARD))
        self.assertEqual(
            SchemaDocument(
                SchemaType.AVRO, json.dumps(PAYMENT), (DocumentReference("shop.Card", card),)
            ),
            document,
        )

    def test_avro_reports_missing_and_cyclic_types(self):
        path = self.write("payment.avsc", PAYMENT)
        with self.assertRaisesRegex(SchemaError, "expected shop.Card.avsc next to the schema"):
            avro_document(path)

        self.write(
            "shop.A.avsc",
            {"type": "record", "name": "shop.A", "fields": [{"name": "b", "type": "shop.B"}]},
        )
        self.write(
            "shop.B.avsc",
            {"type": "record", "name": "shop.B", "fields": [{"name": "a", "type": "shop.A"}]},
        )
        with self.assertRaisesRegex(SchemaError, "reference each other"):
            avro_document(self.directory / "shop.A.avsc")

    def test_json_schema_references_are_named_by_their_path(self):
        self.write("defs/name.json", {"type": "string"})
        path = self.write(
            "user.json",
            {
                "properties": {
                    "name": {"$ref": "defs/name.json#"},
                    "nick": {"$ref": "defs/name.json"},
                }
            },
        )

        document = json_document(path)

        self.assertEqual(SchemaType.JSON, document.type)
        (reference,) = document.references
        self.assertEqual("defs/name.json", reference.name)
        self.assertEqual(json.dumps({"type": "string"}), reference.document.content)

    def test_json_schema_cycles_are_rejected(self):
        self.write("a.json", {"$ref": "b.json"})
        self.write("b.json", {"$ref": "a.json"})

        with self.assertRaisesRegex(SchemaError, "form a cycle"):
            json_document(self.directory / "a.json")

    def test_protobuf_imports_become_references_without_well_known_types(self):
        source = self.proto_files()

        confluent = protobuf_document({"source": source}, "shop.User", as_source=False)
        apicurio = protobuf_document({"source": source}, "shop.User", as_source=True)

        self.assertEqual(["common/address.proto"], [r.name for r in confluent.references])
        root = FileDescriptorProto.FromString(b64decode(confluent.content))
        self.assertEqual("user.proto", root.name)
        self.assertEqual(USER_PROTO, apicurio.content)
        self.assertEqual(ADDRESS_PROTO, apicurio.references[0].document.content)

    def test_protobuf_descriptor_sets_register_only_as_descriptors(self):
        descriptor_path = self.directory / "user.desc"
        descriptor_path.write_bytes(compile_proto_file(self.proto_files()).SerializeToString())
        config = {"descriptor": str(descriptor_path)}

        document = protobuf_document(config, "shop.Address", as_source=False)

        self.assertEqual(
            "common/address.proto", FileDescriptorProto.FromString(b64decode(document.content)).name
        )
        with self.assertRaisesRegex(SchemaError, "needs --protobuf source"):
            protobuf_document(config, "shop.User", as_source=True)
        with self.assertRaisesRegex(SchemaError, "isn't in the schema"):
            protobuf_document(config, "shop.Missing", as_source=False)


class TestProtobufSources(SchemaFiles):
    def test_consumer_and_producer_compile_proto_sources(self):
        config = {"source": self.proto_files(), "value": "shop.User"}
        serializer = SerializerPool(protobuf_config=config).get(Serialization.PROTOBUF, VALUE)

        data = serializer.serialize('{"name": "Ada", "address": {"city": "Quito"}}')

        decoded = ProtobufDeserializer(config).deserialize(data, "users", VALUE)
        self.assertEqual("Ada", decoded["name"])
        self.assertEqual({"city": "Quito"}, decoded["address"])

    def test_invalid_sources_fail(self):
        broken = self.write("broken.proto", 'syntax = "proto3"; message {')

        with self.assertRaisesRegex(SchemaError, "Invalid Protobuf schema"):
            compile_proto_file(broken)
        with self.assertRaisesRegex(SchemaError, "Unable to read"):
            compile_proto_file(self.directory / "missing.proto")


class TestConfluentRegistration(SchemaFiles):
    def setUp(self) -> None:
        super().setUp()
        patcher = patch("kaskade.serializers.registry.SchemaRegistryClient")
        self.addCleanup(patcher.stop)
        self.client = patcher.start().return_value
        self.client.register_schema_full_response.side_effect = [
            SimpleNamespace(schema_id=3, version=None),
            SimpleNamespace(schema_id=8, version=2),
        ]
        self.client.lookup_schema.return_value = SimpleNamespace(version=1)
        self.write("shop.Card.avsc", CARD)
        self.schema_path = self.write("payment.avsc", PAYMENT)

    def serializer(self, **registry: str):
        pool = SerializerPool(
            "payments",
            registry_config={"url": "http://registry", "auto.register.schemas": "true", **registry},
            avro_config={"value": self.schema_path},
        )
        return pool.get(Serialization.REGISTRY, VALUE)

    def test_registers_references_first_and_frames_with_the_returned_id(self):
        registered = SimpleNamespace(
            schema_str=json.dumps(PAYMENT),
            schema_type="AVRO",
            references=[SimpleNamespace(name="shop.Card", subject="shop.Card", version=1)],
        )
        self.client.get_schema.return_value = registered
        self.client.get_version.return_value = SimpleNamespace(
            schema=SimpleNamespace(schema_str=json.dumps(CARD), schema_type="AVRO", references=[])
        )
        serializer = self.serializer(**{"normalize.schemas": "true"})

        with self.assertRaisesRegex(SerializationError, "Registering the schema"):
            serializer.serialize("{}")
        serializer.resolve()
        serializer.resolve()

        card = Schema(json.dumps(CARD), "AVRO", [])
        payment = Schema(
            json.dumps(PAYMENT), "AVRO", [SchemaReference("shop.Card", "shop.Card", 1)]
        )
        self.assertEqual(
            [
                call("shop.Card", card, normalize_schemas=True),
                call("payments-value", payment, normalize_schemas=True),
            ],
            self.client.register_schema_full_response.call_args_list,
        )
        self.client.lookup_schema.assert_called_once_with("shop.Card", card, normalize_schemas=True)
        self.client.get_latest_version.assert_not_called()
        self.assertEqual(
            ("payments-value", "2", 8, "AVRO"), tuple(vars(serializer.schema).values())
        )
        data = serializer.serialize('{"card": {"last4": 1}, "backup": null}')
        self.assertEqual(header(8) + b"\x02\x00", data)

    def test_rejections_are_reported_without_record_content(self):
        self.client.register_schema_full_response.side_effect = [
            SimpleNamespace(schema_id=3, version=1),
            SchemaRegistryError(
                409, 409, "Schema being registered is incompatible with an earlier schema"
            ),
        ]
        serializer = self.serializer()

        with self.assertLogs("kaskade", level="WARNING") as logs:
            serializer.resolve()

        with self.assertRaisesRegex(SerializationError, "incompatible with an earlier schema"):
            serializer.serialize('{"secret": 1}')
        self.assertIn("schema registration failed", "\n".join(logs.output))
        self.assertNotIn("secret", "\n".join(logs.output))

    def test_read_only_credentials_fail_clearly(self):
        self.client.register_schema_full_response.side_effect = SchemaRegistryError(
            403, 40301, "User is denied operation Write on Subject: shop.Card"
        )
        serializer = self.serializer()

        with self.assertLogs("kaskade", level="WARNING"):
            serializer.resolve()

        with self.assertRaisesRegex(SerializationError, "registering needs write access"):
            serializer.serialize("{}")


class TestApicurioRegistration(SchemaFiles):
    def setUp(self) -> None:
        super().setUp()
        patcher = patch("kaskade.serializers.registry.ApicurioClient")
        self.addCleanup(patcher.stop)
        self.client = patcher.start().return_value
        self.client.config.use_id = "contentId"
        self.client.create_version.side_effect = [
            ApicurioVersion("default", "common/address.proto", "1", 40, 4),
            ApicurioVersion("default", "users-value", "3", 41, 5),
        ]

    def serializer(self, **protobuf: str):
        config = APICURIO_CONFIG | {"apicurio.registry.auto-register": "true"}
        pool = SerializerPool(
            "users",
            registry_config=config,
            apicurio_config=ApicurioConfig.from_dict(APICURIO_CONFIG),
            protobuf_config=protobuf,
        )
        return pool.get(Serialization.REGISTRY, VALUE)

    def test_registers_proto_sources_and_frames_with_the_message_reference(self):
        source = self.proto_files()
        self.client.get_artifact.return_value = ApicurioArtifact(
            5,
            "CONTENT_ID",
            USER_PROTO,
            "PROTOBUF",
            (ApicurioReference("common/address.proto", "default", "common/address.proto", "1"),),
        )
        self.client.get_referenced_artifact.return_value = ApicurioArtifact(
            0, "REFERENCE", ADDRESS_PROTO, "PROTOBUF", ()
        )
        serializer = self.serializer(source=source, value="shop.User")

        serializer.resolve()

        self.assertEqual(
            [
                call("default", "common/address.proto", "PROTOBUF", ADDRESS_PROTO, ()),
                call(
                    "default",
                    "users-value",
                    "PROTOBUF",
                    USER_PROTO,
                    (
                        ApicurioReference(
                            "common/address.proto", "default", "common/address.proto", "1"
                        ),
                    ),
                ),
            ],
            self.client.create_version.call_args_list,
        )
        self.client.get_artifact.assert_called_once_with(5)
        type_ref = b"\x06\x0a\x04User"
        self.assertEqual(
            header(5) + type_ref + b"\x0a\x03Ada", serializer.serialize('{"name": "Ada"}')
        )
        self.assertEqual(
            ("users-value", "3", 5, "PROTOBUF"), tuple(vars(serializer.schema).values())
        )

    def test_unauthorized_registration_fails_clearly(self):
        response = httpx.Response(403, request=httpx.Request("POST", APICURIO_URL))
        error = ApicurioRegistryError("Apicurio request failed")
        error.__cause__ = httpx.HTTPStatusError("403", request=response.request, response=response)
        self.client.create_version.side_effect = error
        serializer = self.serializer(source=self.proto_files(), value="shop.User")

        with self.assertLogs("kaskade", level="WARNING"):
            serializer.resolve()

        with self.assertRaisesRegex(SerializationError, "registering needs write access"):
            serializer.serialize("{}")


class TestApicurioClientRegistration(unittest.TestCase):
    @patch("kaskade.apicurio.httpx.Client")
    def test_creates_or_finds_the_version_with_its_references(
        self, client_class: MagicMock
    ) -> None:
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "artifact": {"artifactId": "users-value"},
            "version": {
                "groupId": "shop",
                "artifactId": "users-value",
                "version": "2",
                "globalId": 9,
                "contentId": 4,
            },
        }
        client_class.return_value.request.return_value = response
        client = ApicurioClient(ApicurioConfig.from_dict(APICURIO_CONFIG))
        reference = ApicurioReference("shop.Card", "shop", "shop.Card", "1")

        version = client.create_version("shop", "users-value", "AVRO", "{}", (reference,))

        self.assertEqual(ApicurioVersion("shop", "users-value", "2", 9, 4), version)
        method, path = client_class.return_value.request.call_args.args
        kwargs = client_class.return_value.request.call_args.kwargs
        self.assertEqual(("POST", "/groups/shop/artifacts"), (method, path))
        self.assertEqual({"ifExists": "FIND_OR_CREATE_VERSION"}, kwargs["params"])
        content = kwargs["json"]["firstVersion"]["content"]
        self.assertEqual("application/json", content["contentType"])
        self.assertEqual(
            [{"groupId": "shop", "artifactId": "shop.Card", "version": "1", "name": "shop.Card"}],
            content["references"],
        )

    @patch("kaskade.apicurio.httpx.Client")
    def test_rule_violations_include_the_registry_detail(self, client_class: MagicMock) -> None:
        request = httpx.Request("POST", f"{APICURIO_URL}/groups/default/artifacts")
        client_class.return_value.request.return_value = httpx.Response(
            409, json={"detail": "Incompatible artifact: users-value"}, request=request
        )
        client = ApicurioClient(ApicurioConfig.from_dict(APICURIO_CONFIG))

        with self.assertRaisesRegex(
            ApicurioRegistryError, "(?s)409 Conflict.*; Incompatible artifact"
        ):
            client.create_version("default", "users-value", "AVRO", "{}")


class TestRegistrationValidation(SchemaFiles):
    def options(self, registry: dict[str, str], **configs: dict[str, str]):
        return normalize_serializer_options(
            Serialization.STRING,
            Serialization.REGISTRY,
            registry_config=registry,
            protobuf_config=configs.get("protobuf", {}),
            avro_config=configs.get("avro", {}),
            json_config=configs.get("json", {}),
            bytes_config={},
        )

    def test_a_registering_field_takes_one_schema_file(self):
        avro = self.write("user.avsc", {"type": "record", "name": "User", "fields": []})
        schema = self.write("user.json", {"type": "object"})
        registry = {"url": "http://registry", "value.auto.register.schemas": "true"}

        options = self.options(registry, avro={"value": avro})

        self.assertEqual({"value": avro}, options.avro_config)
        with self.assertRaisesRegex(BadParameter, "needs exactly one schema file"):
            self.options(registry, avro={"value": avro}, json={"value": schema})
        with self.assertRaisesRegex(BadParameter, "is the schema to register; enable"):
            self.options({"url": "http://registry"}, avro={"value": avro})

    def test_apicurio_registers_protobuf_only_from_sources(self):
        source = self.proto_files()
        descriptor = self.directory / "user.desc"
        descriptor.write_bytes(
            FileDescriptorSet(file=compile_proto_file(source).file).SerializeToString()
        )
        registry = APICURIO_CONFIG | {"apicurio.registry.auto-register": "true"}

        options = self.options(registry, protobuf={"source": source, "value": "shop.User"})

        self.assertEqual({"source": source, "value": "shop.User"}, options.protobuf_config)
        with self.assertRaisesRegex(BadParameter, "needs --protobuf source") as raised:
            self.options(registry, protobuf={"descriptor": str(descriptor), "value": "shop.User"})
        self.assertIn("'--protobuf descriptor'", raised.exception.format_message())
        with self.assertRaisesRegex(BadParameter, "either descriptor or source"):
            self.options(
                registry,
                protobuf={"descriptor": str(descriptor), "source": source, "value": "shop.User"},
            )


if __name__ == "__main__":
    unittest.main()
