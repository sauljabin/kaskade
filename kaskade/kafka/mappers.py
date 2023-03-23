import json

from confluent_kafka import Node as NodeMetadata
from confluent_kafka import TopicPartition as GroupPartitionMetadata
from confluent_kafka.admin import BrokerMetadata
from confluent_kafka.admin import ConsumerGroupDescription as GroupMetadata
from confluent_kafka.admin import MemberDescription as MemberMetadata
from confluent_kafka.admin import PartitionMetadata, TopicMetadata
from confluent_kafka.schema_registry import Schema as SchemaMetadata

from kaskade.kafka.models import (
    Broker,
    Group,
    GroupMember,
    GroupPartition,
    Node,
    Partition,
    Schema,
    Topic,
)


def metadata_to_broker(metadata: BrokerMetadata) -> Broker:
    return Broker(id=metadata.id, host=metadata.host, port=metadata.port)


def metadata_to_node(metadata: NodeMetadata) -> Node:
    return Node(id=metadata.id, host=metadata.host, port=metadata.port, rack=metadata.rack)


def metadata_to_group(metadata: GroupMetadata) -> Group:
    return Group(
        id=metadata.group_id,
        broker=metadata_to_node(metadata.coordinator),
        state=str(metadata.state),
        partition_assignor=metadata.partition_assignor,
        members=[],
        partitions=[],
    )


def metadata_to_group_member(group: str, metadata: MemberMetadata) -> GroupMember:
    return GroupMember(
        id=metadata.member_id,
        group=group,
        client_id=metadata.client_id,
        host=metadata.host,
        instance_id=metadata.group_instance_id,
    )


def metadata_to_group_partition(group: str, metadata: GroupPartitionMetadata) -> GroupPartition:
    return GroupPartition(
        id=metadata.partition,
        topic=metadata.topic,
        offset=metadata.offset,
        group=group,
        high=0,
        low=0,
    )


def metadata_to_partition(metadata: PartitionMetadata) -> Partition:
    return Partition(
        id=metadata.id,
        leader=metadata.leader,
        replicas=metadata.replicas,
        isrs=metadata.isrs,
        high=0,
        low=0,
    )


def metadata_to_topic(metadata: TopicMetadata) -> Topic:
    return Topic(
        name=metadata.topic,
        groups=[],
        partitions=[],
    )


def metadata_to_schema(metadata: SchemaMetadata) -> Schema:
    return Schema(
        type=metadata.schema_type,
        json_file=metadata.schema_str,
        data=json.loads(metadata.schema_str),
    )
