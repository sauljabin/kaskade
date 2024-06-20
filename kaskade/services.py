from operator import attrgetter
from typing import List

from confluent_kafka.admin import AdminClient, TopicMetadata, DescribeClusterResult

from kaskade.mappers import metadata_to_cluster
from kaskade.models import Topic, Cluster

DEFAULT_TIMEOUT = 2.0


class ClusterService:
    def __init__(self, config: dict[str, str]) -> None:
        self.config = config.copy()
        self.admin_client = AdminClient(self.config)

    def get(self) -> Cluster:
        cluster_metadata: DescribeClusterResult = self.admin_client.describe_cluster(
            request_timeout=DEFAULT_TIMEOUT
        ).result()

        return metadata_to_cluster(cluster_metadata)


class TopicService:
    def __init__(self, config: dict[str, str]) -> None:
        self.config = config.copy()
        self.admin_client = AdminClient(self.config)

    def list(self) -> List[Topic]:
        topics: List[TopicMetadata] = sorted(
            list(self.admin_client.list_topics(timeout=DEFAULT_TIMEOUT).topics.values()),
            key=attrgetter("topic"),
        )

        print(topics)

        groups: List[str] = [
            group.group_id
            for group in self.admin_client.list_consumer_groups(request_timeout=DEFAULT_TIMEOUT)
            .result()
            .valid
        ]

        print(groups)

        return list()


if __name__ == "__main__":
    dev_config = {"bootstrap.servers": "localhost:19092"}

    cluster_service = ClusterService(dev_config)
    cluster = cluster_service.get()
    print(cluster.id)
    print(cluster.controller)
    print(cluster.nodes)

    topic_service = TopicService(dev_config)
    topic_list = topic_service.list()
    # print(topic_list)
