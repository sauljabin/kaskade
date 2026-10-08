import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click import BadParameter, ClickException, MissingParameter

from kaskade.authentication import OAUTH_CALLBACK
from kaskade.cli.connection import resolve_connection
from kaskade.cli.validation import normalize_deserializer_options, uses
from kaskade.configs import BOOTSTRAP_SERVERS
from kaskade.deserializers import Deserialization

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


if __name__ == "__main__":
    unittest.main()
