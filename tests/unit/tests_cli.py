import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click import BadParameter, ClickException, MissingParameter
from google.protobuf.descriptor_pb2 import FileDescriptorSet

from kaskade.authentication import OAUTH_CALLBACK
from kaskade.cli.connection import resolve_connection
from kaskade.cli.validation import (
    normalize_deserializer_options,
    normalize_serializer_options,
    uses,
)
from kaskade.configs import BOOTSTRAP_SERVERS
from kaskade.deserializers import Deserialization
from kaskade.serializers import Serialization

BYTES = Deserialization.BYTES
STRING = Deserialization.STRING
AVRO = Deserialization.AVRO
PROTOBUF = Deserialization.PROTOBUF


def deserializer_options(
    key: Deserialization = BYTES, value: Deserialization = BYTES, **configs: dict[str, str]
):
    properties = {
        name: configs.get(name, {})
        for name in (
            "registry_config",
            "protobuf_config",
            "avro_config",
            "json_config",
            "bytes_config",
            "fallback_config",
        )
    }
    return normalize_deserializer_options(key, value, **properties)


def serializer_options(
    key: Serialization = Serialization.STRING,
    value: Serialization = Serialization.STRING,
    **configs: dict[str, str],
):
    properties = {
        name: configs.get(name, {})
        for name in (
            "registry_config",
            "protobuf_config",
            "avro_config",
            "json_config",
            "bytes_config",
        )
    }
    return normalize_serializer_options(key, value, **properties)


class SchemaDirectory(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def write(self, name: str, content: str | bytes) -> str:
        path = self.directory / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return str(path)


class TestResolveConnection(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch("kaskade.cli.connection.validate_aws_msk_credentials")
        self.addCleanup(patcher.stop)
        self.validate_credentials = patcher.start()

    def test_cli_properties_override_the_file_and_bootstrap_servers_override_both(self) -> None:
        file_config = {
            "kafka": {BOOTSTRAP_SERVERS: "file:9092", "client.id": "file", "acks": "1"},
            "registry": {"url": "http://file", "provider": "confluent"},
        }
        kafka_config = {BOOTSTRAP_SERVERS: "kafka:9092", "client.id": "cli"}
        registry_config = {"url": "http://cli"}

        connection = resolve_connection(file_config, "flag:9092", kafka_config, {}, registry_config)

        self.assertEqual(
            {BOOTSTRAP_SERVERS: "flag:9092", "client.id": "cli", "acks": "1"},
            connection.kafka_config,
        )
        self.assertEqual({"url": "http://cli", "provider": "confluent"}, connection.registry_config)
        self.assertEqual("file:9092", file_config["kafka"][BOOTSTRAP_SERVERS])
        self.assertEqual({BOOTSTRAP_SERVERS: "kafka:9092", "client.id": "cli"}, kafka_config)

    def test_aws_region_enables_msk_iam(self) -> None:
        connection = resolve_connection({"aws": {"region": "us-east-1"}}, "broker:9092", {}, {})

        self.validate_credentials.assert_called_once_with({"region": "us-east-1"})
        self.assertIn(OAUTH_CALLBACK, connection.kafka_config)

    def test_requires_bootstrap_servers(self) -> None:
        with self.assertRaisesRegex(ClickException, "Bootstrap servers are required"):
            resolve_connection({}, None, {}, {})

    def test_validates_aws_properties_before_checking_credentials(self) -> None:
        with self.assertRaises(MissingParameter):
            resolve_connection({}, "broker:9092", {}, {"region": ""})

        self.validate_credentials.assert_not_called()


class TestDeserializerValidation(unittest.TestCase):
    def test_uses_matches_key_or_value(self) -> None:
        self.assertTrue(uses(AVRO, AVRO, STRING))
        self.assertTrue(uses(AVRO, STRING, AVRO))
        self.assertFalse(uses(AVRO, STRING, STRING))

    def test_returns_normalized_copies_without_mutating_arguments(self) -> None:
        bytes_config = {"encoding": "BASE64"}
        fallback_config = {"encoding": "HEX"}
        json_config = {"framing": "CONFLUENT"}

        options = deserializer_options(
            value=Deserialization.JSON,
            bytes_config=bytes_config,
            fallback_config=fallback_config,
            json_config=json_config,
        )

        self.assertEqual({"encoding": "base64"}, options.bytes_config)
        self.assertEqual({"encoding": "hex"}, options.fallback_config)
        self.assertEqual({"framing": "confluent"}, options.json_config)
        self.assertEqual({"encoding": "BASE64"}, bytes_config)
        self.assertEqual({"encoding": "HEX"}, fallback_config)
        self.assertEqual({"framing": "CONFLUENT"}, json_config)

    def test_normalizes_the_registry_provider_on_a_copy(self) -> None:
        registry_config = {"provider": "CONFLUENT", "url": "http://registry"}

        options = deserializer_options(
            value=Deserialization.REGISTRY, registry_config=registry_config
        )

        self.assertEqual("confluent", options.registry_config["provider"])
        self.assertEqual("CONFLUENT", registry_config["provider"])
        self.assertIsNone(options.apicurio_config)

    def test_avro_and_protobuf_check_usage_first(self) -> None:
        for option, config in (
            ("avro", {"value": "missing.avsc"}),
            ("protobuf", {"value": "MyMessage"}),
        ):
            with self.subTest(option), self.assertRaises(MissingParameter) as raised:
                deserializer_options(value=STRING, **{f"{option}_config": config})
            self.assertIn(f"'-k {option}' and/or '-v {option}'", raised.exception.format_message())

    def test_file_errors_name_the_offending_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cases = (
                (AVRO, {"avro_config": {"value": "missing.avsc"}}, "'missing.avsc' should exist"),
                (
                    PROTOBUF,
                    {"protobuf_config": {"descriptor": directory, "value": "MyMessage"}},
                    f"{directory!r} is a directory",
                ),
            )
            for value, configs, message in cases:
                with self.subTest(value), self.assertRaisesRegex(BadParameter, message) as raised:
                    deserializer_options(value=value, **configs)
                self.assertIn(f"--{value}", raised.exception.format_message())

    def test_accepts_existing_schema_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "value.avsc"
            schema.write_text("{}")

            options = deserializer_options(value=AVRO, avro_config={"value": str(schema)})

        self.assertEqual({"value": str(schema)}, options.avro_config)


class TestJsonSchemaValidation(SchemaDirectory):
    def test_consumer_accepts_a_json_schema_per_field(self) -> None:
        schema = self.write("user.json", '{"type": "object"}')

        options = deserializer_options(
            value=Deserialization.JSON, json_config={"value": schema, "framing": "RAW"}
        )

        self.assertEqual({"value": schema, "framing": "raw"}, options.json_config)

    def test_a_schema_applies_only_to_a_json_field(self) -> None:
        schema = self.write("user.json", '{"type": "object"}')

        with self.assertRaisesRegex(BadParameter, "--json key requires '-k json'"):
            deserializer_options(
                key=STRING, value=Deserialization.JSON, json_config={"key": schema}
            )
        with self.assertRaisesRegex(BadParameter, "--json value requires '-v json'"):
            serializer_options(key=Serialization.JSON, json_config={"value": schema})

    def test_unusable_schemas_fail_as_json_errors(self) -> None:
        cases = (
            (self.write("broken.json", "{"), "Invalid JSON in"),
            (self.write("invalid.json", '{"type": 5}'), "Invalid JSON Schema"),
            (str(self.directory / "missing.json"), "should exist"),
        )
        for schema, message in cases:
            for options, json_format in (
                (deserializer_options, Deserialization.JSON),
                (serializer_options, Serialization.JSON),
            ):
                with (
                    self.subTest(schema=schema, json_format=json_format),
                    self.assertRaisesRegex(BadParameter, message) as raised,
                ):
                    options(value=json_format, json_config={"value": schema})
                self.assertIn("'--json value'", raised.exception.format_message())


class TestSerializerValidation(SchemaDirectory):
    def test_returns_normalized_copies_without_mutating_arguments(self) -> None:
        registry_config = {
            "provider": "APICURIO",
            "apicurio.registry.url": "http://registry/apis/registry/v3",
            "value.apicurio.registry.artifact.artifact-id": "orders",
            "apicurio.registry.auto-register": "false",
        }
        bytes_config = {"key.encoding": "HEX"}

        options = serializer_options(
            key=Serialization.BYTES,
            value=Serialization.REGISTRY,
            registry_config=registry_config,
            bytes_config=bytes_config,
        )

        self.assertEqual("apicurio", options.registry_config["provider"])
        self.assertEqual(
            "orders", options.registry_config["value.apicurio.registry.artifact.artifact-id"]
        )
        self.assertEqual("http://registry/apis/registry/v3", options.apicurio_config.url)
        self.assertEqual({"key.encoding": "hex"}, options.bytes_config)
        self.assertEqual("APICURIO", registry_config["provider"])
        self.assertEqual({"key.encoding": "HEX"}, bytes_config)

    def test_rejects_unsupported_schema_selection(self) -> None:
        cases = (
            (
                {"url": "http://registry", "auto.register.schemas": "true"},
                "needs exactly one schema file",
            ),
            (
                {"url": "http://registry", "use.latest.version": "false"},
                "needs auto.register.schemas=true",
            ),
            (
                {"url": "http://registry", "apicurio.registry.artifact.artifact-id": "orders"},
                "requires provider=apicurio",
            ),
        )
        for registry_config, message in cases:
            with (
                self.subTest(registry_config),
                self.assertRaisesRegex(BadParameter, message) as raised,
            ):
                serializer_options(value=Serialization.REGISTRY, registry_config=registry_config)
            self.assertIn("--registry", raised.exception.format_message())

    def test_scoped_selection_requires_that_field_to_use_the_registry(self) -> None:
        with self.assertRaisesRegex(
            BadParameter, "--registry key.use.schema.id requires '-k registry'"
        ):
            serializer_options(
                value=Serialization.REGISTRY,
                registry_config={"url": "http://registry", "key.use.schema.id": "3"},
            )

    def test_requires_the_schema_files_each_format_needs(self) -> None:
        avro = self.write("user.avsc", '{"type": "record", "name": "User", "fields": []}')
        cases = (
            ({"value": Serialization.AVRO}, {}, MissingParameter, "--avro"),
            (
                {"value": Serialization.AVRO, "key": Serialization.AVRO},
                {"avro_config": {"value": avro}},
                MissingParameter,
                "--avro key=",
            ),
            (
                {"value": Serialization.AVRO},
                {"avro_config": {"value": avro, "framing": "confluent"}},
                BadParameter,
                "Valid properties",
            ),
            (
                {"value": Serialization.PROTOBUF},
                {"protobuf_config": {"value": "User"}},
                MissingParameter,
                "--protobuf descriptor=",
            ),
            (
                {"value": Serialization.REGISTRY},
                {},
                ClickException,
                "Schema Registry configuration is required",
            ),
            (
                {},
                {"bytes_config": {"encoding": "hex"}},
                MissingParameter,
                "'-k bytes' and/or '-v bytes'",
            ),
        )
        for formats, configs, error, message in cases:
            with self.subTest(formats=formats, configs=configs), self.assertRaises(error) as raised:
                serializer_options(**formats, **configs)
            self.assertIn(message, raised.exception.format_message())

    def test_loads_schema_files_before_the_tui_opens(self) -> None:
        descriptor = self.write("user.desc", FileDescriptorSet().SerializeToString())
        broken = self.write("broken.avsc", "{")

        with self.assertRaisesRegex(BadParameter, "Invalid Avro schema") as raised:
            serializer_options(value=Serialization.AVRO, avro_config={"value": broken})
        self.assertIn("'--avro value'", raised.exception.format_message())
        with self.assertRaisesRegex(BadParameter, "User isn't in") as raised:
            serializer_options(
                key=Serialization.PROTOBUF,
                protobuf_config={"descriptor": descriptor, "key": "User"},
            )
        self.assertIn("'--protobuf key'", raised.exception.format_message())


if __name__ == "__main__":
    unittest.main()
