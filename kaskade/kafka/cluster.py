import concurrent
from typing import Optional

from confluent_kafka.admin import RESOURCE_BROKER, AdminClient, ConfigResource

from kaskade.config import Config
from kaskade.kafka import TIMEOUT


class Cluster:
    def __init__(
        self,
        brokers: Optional[int] = None,
        version: Optional[str] = None,
        has_schemas: Optional[bool] = None,
        protocol: Optional[str] = None,
    ) -> None:
        self.brokers = brokers
        self.version = version
        self.has_schemas = has_schemas
        self.protocol = protocol

    def __str__(self) -> str:
        return str(
            {
                "brokers": [str(broker) for broker in self.brokers],
                "version": self.version,
                "has_schemas": self.has_schemas,
                "protocol": self.protocol,
            }
        )


class ClusterService:
    def __init__(self, config: Optional[Config]) -> None:
        if not config or not config.kafka:
            raise Exception("Config not found")
        self.config = config

    def cluster(self) -> Cluster:
        version = "unknown"
        has_schemas = bool(self.config.schema_registry)
        security_protocol = self.config.kafka.get("security.protocol")
        protocol = security_protocol.lower() if security_protocol else "plain"

        admin_client = AdminClient(self.config.kafka)
        brokers = list(admin_client.list_topics(timeout=TIMEOUT).brokers.values())
        brokers.sort(key=lambda broker: broker.id)

        if brokers:
            config_to_describe = [ConfigResource(RESOURCE_BROKER, str(brokers[0].id))]
            future_config = admin_client.describe_configs(config_to_describe)
            future_as_completed = concurrent.futures.as_completed(
                iter(future_config.values())
            )
            task = next(future_as_completed)
            task_result = task.result(timeout=TIMEOUT)

            if task_result:
                protocol_version = task_result.get("inter.broker.protocol.version")
                if protocol_version:
                    version = protocol_version.value.split("-")[0]

        return Cluster(
            brokers=brokers, protocol=protocol, version=version, has_schemas=has_schemas
        )


if __name__ == "__main__":

    class Config:
        kafka = {"bootstrap.servers": "localhost:9093"}

    config = Config()
    cluster_service = ClusterService(config)
    cluster = cluster_service.cluster()
    print(cluster)
