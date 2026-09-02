import json
import struct
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import httpx
from confluent_kafka.serialization import MessageField
from fastavro import schemaless_writer
from google.protobuf.descriptor_pb2 import FieldDescriptorProto, FileDescriptorProto
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message_factory import GetMessageClass

from kaskade.apicurio import (
    APICURIO_CHECK_PERIOD,
    APICURIO_CLIENT_ID,
    APICURIO_CLIENT_SECRET,
    APICURIO_PASSWORD,
    APICURIO_PROXY_HOST,
    APICURIO_PROXY_PASSWORD,
    APICURIO_PROXY_PORT,
    APICURIO_PROXY_USERNAME,
    APICURIO_RETRY_BACKOFF,
    APICURIO_RETRY_COUNT,
    APICURIO_TLS_CLIENT_CERTIFICATE,
    APICURIO_TLS_CLIENT_KEY,
    APICURIO_TOKEN_ENDPOINT,
    APICURIO_URL,
    APICURIO_USE_ID,
    APICURIO_USERNAME,
    ApicurioArtifact,
    ApicurioClient,
    ApicurioConfig,
    ApicurioReference,
    ApicurioRegistryError,
)
from kaskade.configs import APICURIO
from kaskade.deserializers import (
    ApicurioRegistryDeserializer,
    ConfluentRegistryDeserializer,
    DeserializationError,
    RegistryDeserializer,
)


def apicurio_config(**overrides: str) -> dict[str, str]:
    return {"provider": APICURIO, APICURIO_URL: "http://registry/apis/registry/v3"} | overrides


def varint(value: int) -> bytes:
    result = bytearray()
    while True:
        current = value & 0x7F
        value >>= 7
        result.append(current | (0x80 if value else 0))
        if not value:
            return bytes(result)


def type_ref(name: str) -> bytes:
    encoded = name.encode()
    message = b"\x0a" + varint(len(encoded)) + encoded
    return varint(len(message)) + message


class TestApicurioConfig(unittest.TestCase):
    def test_defaults_and_case_insensitive_id_kind(self) -> None:
        config = ApicurioConfig.from_dict(apicurio_config(**{APICURIO_USE_ID: "GLOBALID"}))

        self.assertEqual("globalId", config.use_id)
        self.assertEqual(30000, config.check_period_ms)
        self.assertEqual(3, config.retry_count)
        self.assertEqual(300, config.retry_backoff_ms)

    def test_accepts_basic_authentication_and_proxy(self) -> None:
        config = ApicurioConfig.from_dict(
            apicurio_config(
                **{
                    APICURIO_USERNAME: "reader",
                    APICURIO_PASSWORD: "secret",
                    APICURIO_PROXY_HOST: "proxy.example.com",
                    APICURIO_PROXY_PORT: "8080",
                    APICURIO_PROXY_USERNAME: "proxy user",
                    APICURIO_PROXY_PASSWORD: "p@ss",
                }
            )
        )

        self.assertEqual("reader", config.username)
        self.assertEqual("http://proxy%20user:p%40ss@proxy.example.com:8080", config.proxy)

    def test_rejects_incomplete_or_mixed_authentication(self) -> None:
        with self.assertRaisesRegex(ApicurioRegistryError, "Incomplete OAuth"):
            ApicurioConfig.from_dict(apicurio_config(**{APICURIO_CLIENT_ID: "client"}))

        with self.assertRaisesRegex(ApicurioRegistryError, "cannot be configured together"):
            ApicurioConfig.from_dict(
                apicurio_config(
                    **{
                        APICURIO_USERNAME: "reader",
                        APICURIO_PASSWORD: "secret",
                        APICURIO_TOKEN_ENDPOINT: "http://idp/token",
                        APICURIO_CLIENT_ID: "client",
                        APICURIO_CLIENT_SECRET: "secret",
                    }
                )
            )

    def test_rejects_aliases_and_unsupported_stores(self) -> None:
        with self.assertRaisesRegex(ApicurioRegistryError, "Unrecognized Apicurio properties: url"):
            ApicurioConfig.from_dict(apicurio_config(url="http://alias"))
        with self.assertRaisesRegex(ApicurioRegistryError, "JKS and PKCS12"):
            ApicurioConfig.from_dict(
                apicurio_config(**{"apicurio.registry.tls.keystore.type": "JKS"})
            )

    def test_validates_numeric_boolean_and_pem_pairs(self) -> None:
        with self.assertRaisesRegex(ApicurioRegistryError, "must be an integer"):
            ApicurioConfig.from_dict(apicurio_config(**{APICURIO_RETRY_COUNT: "many"}))
        with self.assertRaisesRegex(ApicurioRegistryError, "must be true or false"):
            ApicurioConfig.from_dict(apicurio_config(**{"apicurio.registry.tls.trust-all": "yes"}))
        with self.assertRaisesRegex(ApicurioRegistryError, "configured together"):
            ApicurioConfig.from_dict(
                apicurio_config(**{APICURIO_TLS_CLIENT_CERTIFICATE: "client.pem"})
            )

        with tempfile.TemporaryDirectory() as directory:
            certificate = Path(directory) / "client.pem"
            key = Path(directory) / "client.key"
            certificate.touch()
            key.touch()
            config = ApicurioConfig.from_dict(
                apicurio_config(
                    **{
                        APICURIO_TLS_CLIENT_CERTIFICATE: str(certificate),
                        APICURIO_TLS_CLIENT_KEY: str(key),
                    }
                )
            )
            self.assertEqual((str(certificate), str(key)), config.certificate)


class TestApicurioClient(unittest.TestCase):
    @patch("kaskade.apicurio.httpx.Client")
    def test_fetches_artifact_references_metadata_and_caches(self, client_class: MagicMock) -> None:
        content_response = MagicMock(
            text='{"type":"record","name":"User","fields":[]}',
            headers={"X-Registry-ArtifactType": "AVRO"},
            status_code=200,
        )
        references_response = MagicMock(status_code=200)
        references_response.json.return_value = [
            {
                "name": "common.avsc",
                "groupId": "shared",
                "artifactId": "common",
                "version": "2",
            }
        ]
        metadata_response = MagicMock(status_code=200)
        metadata_response.json.return_value = {
            "count": 1,
            "artifacts": [{"groupId": "default", "artifactId": "users-value", "version": "1"}],
        }
        client_class.return_value.request.side_effect = [
            content_response,
            references_response,
            metadata_response,
        ]
        client = ApicurioClient(apicurio_config())

        first = client.get_artifact(7)
        second = client.get_artifact(7)
        metadata = client.get_metadata(7)

        self.assertIs(first, second)
        self.assertEqual("CONTENT_ID", first.id_kind)
        self.assertEqual("common.avsc", first.references[0].name)
        self.assertEqual("users-value", metadata[0]["artifactId"])
        self.assertEqual(
            [
                call(
                    "GET",
                    "/ids/contentIds/7",
                    headers={},
                    params={"returnArtifactType": "true"},
                ),
                call("GET", "/ids/contentIds/7/references", headers={}),
                call(
                    "GET",
                    "/search/versions",
                    headers={},
                    params={"contentId": 7, "limit": 100, "offset": 0},
                ),
            ],
            client_class.return_value.request.call_args_list,
        )

    @patch("kaskade.apicurio.httpx.Client")
    def test_oauth_token_is_lazy_cached_and_refreshed_once_after_401(
        self, client_class: MagicMock
    ) -> None:
        token_one = MagicMock(status_code=200)
        token_one.json.return_value = {"access_token": "one", "expires_in": 3600}
        token_two = MagicMock(status_code=200)
        token_two.json.return_value = {"access_token": "two", "expires_in": 3600}
        client_class.return_value.post.side_effect = [token_one, token_two]
        unauthorized = MagicMock(status_code=401)
        success = MagicMock(status_code=200)
        client_class.return_value.request.side_effect = [unauthorized, success]
        client = ApicurioClient(
            apicurio_config(
                **{
                    APICURIO_TOKEN_ENDPOINT: "http://idp/token",
                    APICURIO_CLIENT_ID: "reader",
                    APICURIO_CLIENT_SECRET: "secret",
                    APICURIO_RETRY_COUNT: "0",
                }
            )
        )

        result = client._request("GET", "/groups")

        self.assertIs(success, result)
        self.assertEqual(2, client_class.return_value.post.call_count)
        self.assertEqual(
            ("reader", "secret"), client_class.return_value.post.call_args.kwargs["auth"]
        )
        self.assertEqual(
            ["Bearer one", "Bearer two"],
            [
                request.kwargs["headers"]["Authorization"]
                for request in client_class.return_value.request.call_args_list
            ],
        )

    @patch("kaskade.apicurio.time.sleep")
    @patch("kaskade.apicurio.httpx.Client")
    def test_retries_server_errors_with_configured_backoff(
        self, client_class: MagicMock, sleep: MagicMock
    ) -> None:
        unavailable = MagicMock(status_code=503)
        success = MagicMock(status_code=200)
        client_class.return_value.request.side_effect = [unavailable, success]
        client = ApicurioClient(
            apicurio_config(**{APICURIO_RETRY_COUNT: "1", APICURIO_RETRY_BACKOFF: "25"})
        )

        self.assertIs(success, client._request("GET", "/groups"))
        sleep.assert_called_once_with(0.025)

    @patch("kaskade.apicurio.time.sleep")
    @patch("kaskade.apicurio.httpx.Client")
    def test_retry_exhaustion_is_normalized(
        self, client_class: MagicMock, sleep: MagicMock
    ) -> None:
        request = httpx.Request("GET", "http://registry/groups")
        client_class.return_value.request.side_effect = [
            httpx.ConnectError("offline", request=request),
            httpx.ConnectError("still offline", request=request),
        ]
        client = ApicurioClient(apicurio_config(**{APICURIO_RETRY_COUNT: "1"}))

        with self.assertRaisesRegex(ApicurioRegistryError, "Apicurio request failed"):
            client._request("GET", "/groups")

        sleep.assert_called_once_with(0.3)

    @patch("kaskade.apicurio.httpx.Client")
    def test_zero_check_period_bypasses_cache(self, client_class: MagicMock) -> None:
        content = MagicMock(text="{}", headers={"X-Registry-ArtifactType": "JSON"}, status_code=200)
        references = MagicMock(status_code=200)
        references.json.return_value = []
        client_class.return_value.request.side_effect = [
            content,
            references,
            content,
            references,
        ]
        client = ApicurioClient(apicurio_config(**{APICURIO_CHECK_PERIOD: "0"}))

        client.get_artifact(1)
        client.get_artifact(1)

        self.assertEqual(4, client_class.return_value.request.call_count)

    @patch("kaskade.apicurio.httpx.Client")
    def test_global_id_uses_global_endpoints(self, client_class: MagicMock) -> None:
        content = MagicMock(text="{}", headers={"X-Registry-ArtifactType": "JSON"}, status_code=200)
        references = MagicMock(status_code=200)
        references.json.return_value = []
        client_class.return_value.request.side_effect = [content, references]
        client = ApicurioClient(apicurio_config(**{APICURIO_USE_ID: "globalId"}))

        artifact = client.get_artifact(27)

        self.assertEqual("GLOBAL_ID", artifact.id_kind)
        self.assertEqual(
            "/ids/globalIds/27", client_class.return_value.request.call_args_list[0].args[1]
        )
        self.assertEqual(
            "/ids/globalIds/27/references",
            client_class.return_value.request.call_args_list[1].args[1],
        )

    @patch("kaskade.apicurio.httpx.Client")
    def test_cache_is_bounded(self, client_class: MagicMock) -> None:
        client = ApicurioClient(apicurio_config())

        for index in range(client.CACHE_CAPACITY + 1):
            client._store(("schema", index), index)

        self.assertEqual(client.CACHE_CAPACITY, len(client._cache))
        self.assertNotIn(("schema", 0), client._cache)


class TestApicurioDeserializer(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch("kaskade.deserializers.ApicurioClient")
        self.addCleanup(patcher.stop)
        self.client_class = patcher.start()
        self.client = self.client_class.return_value
        self.deserializer = ApicurioRegistryDeserializer(apicurio_config())

    def test_factory_defaults_to_confluent_and_selects_apicurio(self) -> None:
        with patch("kaskade.deserializers.SchemaRegistryClient"):
            confluent = RegistryDeserializer({})
            self.assertIsInstance(confluent._backend, ConfluentRegistryDeserializer)
        apicurio = RegistryDeserializer(apicurio_config())
        self.assertIsInstance(apicurio._backend, ApicurioRegistryDeserializer)
        with self.assertRaisesRegex(DeserializationError, "Unsupported registry provider"):
            RegistryDeserializer({"provider": "OTHER"})

    def test_deserializes_json_with_default_type_reference(self) -> None:
        self.client.get_artifact.return_value = ApicurioArtifact(42, "CONTENT_ID", "{}", "JSON", ())
        payload = json.dumps({"name": "Ada"}).encode()

        result = self.deserializer.deserialize(
            struct.pack(">I", 42) + type_ref("User") + payload,
            "users",
            MessageField.VALUE,
        )

        self.assertEqual({"name": "Ada"}, result)

    def test_json_schema_resolves_references_and_rejects_invalid_content(self) -> None:
        reference = ApicurioReference("https://example.com/name.json", "shared", "name", "1")
        root_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"name": {"$ref": reference.name}},
            "required": ["name"],
        }
        referenced_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "string",
        }
        self.client.get_artifact.return_value = ApicurioArtifact(
            43, "CONTENT_ID", json.dumps(root_schema), "JSON", (reference,)
        )
        self.client.get_referenced_artifact.return_value = ApicurioArtifact(
            0, "REFERENCE", json.dumps(referenced_schema), "JSON", ()
        )

        result = self.deserializer.deserialize(
            struct.pack(">I", 43) + b'{"name":"Ada"}', "users", MessageField.VALUE
        )

        self.assertEqual({"name": "Ada"}, result)
        with self.assertRaisesRegex(DeserializationError, "JSON Schema validation failed"):
            self.deserializer.deserialize(
                struct.pack(">I", 43) + b'{"name":7}', "users", MessageField.VALUE
            )
        self.client.get_referenced_artifact.assert_called_once_with(reference, "JSON")

    def test_deserializes_avro(self) -> None:
        schema = {
            "type": "record",
            "name": "User",
            "fields": [{"name": "name", "type": "string"}],
        }
        output = BytesIO()
        schemaless_writer(output, schema, {"name": "Ada"})
        self.client.get_artifact.return_value = ApicurioArtifact(
            12, "CONTENT_ID", json.dumps(schema), "AVRO", ()
        )

        result = self.deserializer.deserialize(
            struct.pack(">I", 12) + output.getvalue(), "users", MessageField.VALUE
        )

        self.assertEqual({"name": "Ada"}, result)

    def test_deserializes_protobuf_source_and_type_reference(self) -> None:
        source = 'syntax = "proto3"; package people; message User { string name = 1; }'
        descriptor = FileDescriptorProto(name="user.proto", package="people", syntax="proto3")
        message = descriptor.message_type.add(name="User")
        message.field.add(
            name="name",
            number=1,
            label=FieldDescriptorProto.LABEL_OPTIONAL,
            type=FieldDescriptorProto.TYPE_STRING,
        )
        pool = DescriptorPool()
        pool.Add(descriptor)
        user_class = GetMessageClass(pool.FindMessageTypeByName("people.User"))
        self.client.get_artifact.return_value = ApicurioArtifact(
            9, "CONTENT_ID", source, "PROTOBUF", ()
        )

        result = self.deserializer.deserialize(
            struct.pack(">I", 9)
            + type_ref("people.User")
            + user_class(name="Ada").SerializeToString(),
            "users",
            MessageField.VALUE,
        )

        self.assertEqual({"name": "Ada"}, result)

    def test_protobuf_resolves_referenced_sources(self) -> None:
        root_source = """
            syntax = "proto3";
            package people;
            import "address.proto";
            message User { Address address = 1; }
        """
        address_source = """
            syntax = "proto3";
            package people;
            message Address { string city = 1; }
        """
        reference = ApicurioReference("address.proto", "shared", "address", "1")
        self.client.get_artifact.return_value = ApicurioArtifact(
            10, "CONTENT_ID", root_source, "PROTOBUF", (reference,)
        )
        self.client.get_referenced_artifact.return_value = ApicurioArtifact(
            0, "REFERENCE", address_source, "PROTOBUF", ()
        )
        address_descriptor = FileDescriptorProto(
            name="address.proto", package="people", syntax="proto3"
        )
        address = address_descriptor.message_type.add(name="Address")
        address.field.add(
            name="city",
            number=1,
            label=FieldDescriptorProto.LABEL_OPTIONAL,
            type=FieldDescriptorProto.TYPE_STRING,
        )
        user_descriptor = FileDescriptorProto(
            name="user.proto",
            package="people",
            syntax="proto3",
            dependency=["address.proto"],
        )
        user = user_descriptor.message_type.add(name="User")
        user.field.add(
            name="address",
            number=1,
            label=FieldDescriptorProto.LABEL_OPTIONAL,
            type=FieldDescriptorProto.TYPE_MESSAGE,
            type_name=".people.Address",
        )
        pool = DescriptorPool()
        pool.Add(address_descriptor)
        pool.Add(user_descriptor)
        user_class = GetMessageClass(pool.FindMessageTypeByName("people.User"))
        value = user_class()
        value.address.city = "Quito"

        result = self.deserializer.deserialize(
            struct.pack(">I", 10) + type_ref("people.User") + value.SerializeToString(),
            "users",
            MessageField.VALUE,
        )

        self.assertEqual({"address": {"city": "Quito"}}, result)
        self.client.get_referenced_artifact.assert_called_once_with(reference, "PROTOBUF")

    def test_returns_apicurio_metadata_with_provider_discriminator(self) -> None:
        self.client.get_artifact.return_value = ApicurioArtifact(42, "CONTENT_ID", "{}", "JSON", ())
        self.client.get_metadata.return_value = [
            {"groupId": "default", "artifactId": "orders-value", "version": "1"}
        ]

        result = self.deserializer.deserialize_with_metadata(
            struct.pack(">I", 42) + b"{}", "orders", MessageField.VALUE
        )

        self.assertIsNotNone(result.schema)
        self.assertEqual(
            {
                "provider": APICURIO,
                "id": 42,
                "id_kind": "CONTENT_ID",
                "group": "default",
                "artifact": "orders-value",
                "version": "1",
                "type": "JSON",
            },
            result.schema.dict(),
        )

    def test_rejects_short_native_framing(self) -> None:
        with self.assertRaisesRegex(DeserializationError, "Apicurio data framing"):
            self.deserializer.deserialize(b"\x00\x00\x00\x01", "orders", MessageField.VALUE)


if __name__ == "__main__":
    unittest.main()
