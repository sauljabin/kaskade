from operator import attrgetter

from confluent_kafka.admin import RESOURCE_BROKER, AdminClient, ConfigResource

from kaskade.config import Config
from kaskade.kafka import TIMEOUT
from kaskade.kafka.mappers import metadata_to_broker
from kaskade.kafka.models import Cluster


class ClusterService:
    def __init__(self, config: Config) -> None:
        if config is None or config.kafka is None:
            raise Exception("Config not found")
        self.config = config

    def current(self) -> Cluster:
        version = "unknown"
        has_schemas = bool(self.config.schema_registry)
        security_protocol = self.config.kafka.get("security.protocol")
        protocol = security_protocol.lower() if security_protocol else "plain"
        admin_client = AdminClient(self.config.kafka)

        brokers = list(admin_client.list_topics(timeout=TIMEOUT).brokers.values())
        brokers = sorted(brokers, key=attrgetter("id"))
        brokers = list(map(metadata_to_broker, brokers))

        if len(brokers) > 0:
            config_to_describe = [ConfigResource(RESOURCE_BROKER, str(brokers[0].id))]
            future_config = admin_client.describe_configs(config_to_describe)
            list_tasks = list(future_config.values())
            task = list_tasks[0]
            task_result = task.result(timeout=TIMEOUT)

            if task_result:
                protocol_version = task_result.get("inter.broker.protocol.version")
                if protocol_version:
                    version = protocol_version.value.split("-")[0]

        return Cluster(
            brokers=brokers, protocol=protocol, version=version, has_schemas=has_schemas
        )


if __name__ == "__main__":
    config = Config("../../kaskade.yml")
    cluster_service = ClusterService(config)
    print(cluster_service.current())
