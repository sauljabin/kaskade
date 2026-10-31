from enum import StrEnum

MILLISECONDS_24H = 86400000
MILLISECONDS_1W = 604800000
MIN_INSYNC_REPLICAS_CONFIG = "min.insync.replicas"
RETENTION_MS_CONFIG = "retention.ms"
CLEANUP_POLICY_CONFIG = "cleanup.policy"
FRAMING_CONFIGS = ("framing", "key.framing", "value.framing")
SCHEMA_FILE_CONFIGS = ("key", "value")
PROTOBUF_SCHEMA_CONFIGS = ("descriptor", "source")
PROTOBUF_INCLUDE = "include"
PROTOBUF_DESERIALIZER_CONFIGS = (
    *PROTOBUF_SCHEMA_CONFIGS,
    PROTOBUF_INCLUDE,
    *SCHEMA_FILE_CONFIGS,
    *FRAMING_CONFIGS,
)
AVRO_DESERIALIZER_CONFIGS = (*SCHEMA_FILE_CONFIGS, *FRAMING_CONFIGS)
JSON_DESERIALIZER_CONFIGS = (*SCHEMA_FILE_CONFIGS, *FRAMING_CONFIGS)
PROTOBUF_SERIALIZER_CONFIGS = (*PROTOBUF_SCHEMA_CONFIGS, PROTOBUF_INCLUDE, *SCHEMA_FILE_CONFIGS)
AVRO_SERIALIZER_CONFIGS = SCHEMA_FILE_CONFIGS
JSON_SERIALIZER_CONFIGS = SCHEMA_FILE_CONFIGS
APICURIO = "APICURIO"
CONFLUENT = "CONFLUENT"
APICURIO_OPTION = APICURIO.lower()
CONFLUENT_OPTION = CONFLUENT.lower()
REGISTRY_PROVIDERS = (APICURIO_OPTION, CONFLUENT_OPTION)
DESERIALIZER_FRAMINGS = ("raw", *REGISTRY_PROVIDERS)
BYTES_CONFIGS = ("encoding", "key.encoding", "value.encoding")
FALLBACK_CONFIGS = ("encoding",)
BYTES_ENCODINGS = ("base64", "hex", "byte-array", "escaped")
AWS_CONFIGS = ("region",)
# Confluent serializer properties that choose the schema; only the producer accepts them.
AUTO_REGISTER_SCHEMAS = "auto.register.schemas"
USE_LATEST_VERSION = "use.latest.version"
USE_SCHEMA_ID = "use.schema.id"
NORMALIZE_SCHEMAS = "normalize.schemas"
# Kaskade's own property naming the Protobuf message a Registry schema encodes.
PROTOBUF_MESSAGE = "protobuf.message"
SCHEMA_REGISTRY_MAGIC_BYTE = 0
SCHEMA_REGISTRY_HEADER_SIZE = 5
BOOTSTRAP_SERVERS = "bootstrap.servers"
AUTO_OFFSET_RESET = "auto.offset.reset"
EARLIEST = "earliest"
LOGGER = "logger"
MAX_POLL_INTERVAL_MS = "max.poll.interval.ms"
ENABLE_AUTO_COMMIT = "enable.auto.commit"
GROUP_ID = "group.id"


class SchemaType(StrEnum):
    """Schema formats supported by the Registry deserializers."""

    AVRO = "AVRO"
    JSON = "JSON"
    PROTOBUF = "PROTOBUF"


ACKS = "acks"
ACKS_CHOICES = ("all", "-1", "0", "1")
COMPRESSION_TYPE = "compression.type"
COMPRESSION_TYPES = ("none", "gzip", "snappy", "lz4", "zstd")
IDEMPOTENCE_CHOICES = ("true", "false")
ENABLE_IDEMPOTENCE = "enable.idempotence"
# confluent-kafka's defaults, which it can't report back; shown when nothing sets them.
PRODUCER_SETTING_DEFAULTS = {ACKS: "all", COMPRESSION_TYPE: "none", ENABLE_IDEMPOTENCE: "false"}
# librdkafka's older names for the same properties.
PRODUCER_SETTING_ALIASES = {ACKS: "request.required.acks", COMPRESSION_TYPE: "compression.codec"}
