from confluent_kafka import Node as NodeMetadata
from confluent_kafka.admin import DescribeClusterResult as ClusterMetadata

from kaskade.models import Node, Cluster


def metadata_to_node(metadata: NodeMetadata) -> Node:
    return Node(id=metadata.id, host=metadata.host, port=metadata.port, rack=metadata.rack)


def metadata_to_cluster(metadata: ClusterMetadata) -> Cluster:
    return Cluster(
        metadata.cluster_id,
        controller=metadata_to_node(metadata.controller),
        nodes=[metadata_to_node(node_metadata) for node_metadata in metadata.nodes],
    )
