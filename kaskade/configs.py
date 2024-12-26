MILLISECONDS_24H = 86400000
MILLISECONDS_1W = 604800000
MIN_INSYNC_REPLICAS_CONFIG = "min.insync.replicas"
RETENTION_MS_CONFIG = "retention.ms"
CLEANUP_POLICY_CONFIG = "cleanup.policy"
SCHEMA_REGISTRY_CONFIGS = [
    "url",
    "ssl.ca.location",
    "ssl.key.location",
    "ssl.certificate.location",
    "basic.auth.user.info",
]
PROTOBUF_DESERIALIZER_CONFIGS = ["descriptor", "key", "value"]
AVRO_DESERIALIZER_CONFIGS = ["key", "value"]
SCHEMA_REGISTRY_MAGIC_BYTE = 0
BOOTSTRAP_SERVERS = "bootstrap.servers"
AUTO_OFFSET_RESET = "auto.offset.reset"
EARLIEST = "earliest"
LOGGER = "logger"
MAX_POLL_INTERVAL_MS = "max.poll.interval.ms"
ENABLE_AUTO_COMMIT = "enable.auto.commit"
GROUP_ID = "group.id"
