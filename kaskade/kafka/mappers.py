from confluent_kafka.admin import (
    BrokerMetadata,
    GroupMetadata,
    PartitionMetadata,
    TopicMetadata,
)

from kaskade.kafka.models import Broker, Group, Partition, Topic


def metadata_to_broker(metadata: BrokerMetadata) -> Broker:
    return Broker(id=metadata.id, host=metadata.host, port=metadata.port)


def metadata_to_group(metadata: GroupMetadata) -> Group:
    return Group(
        id=metadata.id,
        broker=metadata_to_broker(metadata.broker),
        state=metadata.state,
        members=len(metadata.members),
    )


def metadata_to_partition(metadata: PartitionMetadata) -> Partition:
    return Partition(
        id=metadata.id,
        leader=metadata.leader,
        replicas=metadata.replicas,
        isrs=metadata.isrs,
    )


def metadata_to_topic(metadata: TopicMetadata) -> Topic:
    name = metadata.topic
    return Topic(
        name=name,
        partitions=list(map(metadata_to_partition, metadata.partitions.values())),
    )
