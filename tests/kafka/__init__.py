from confluent_kafka import Node, TopicPartition
from confluent_kafka.admin import (
    BrokerMetadata,
    ConsumerGroupDescription,
    GroupMember,
    PartitionMetadata,
    TopicMetadata,
)

from kaskade.kafka.models import Broker, Cluster, Group, Partition, Topic
from tests import faker


def random_broker(id=faker.pyint()):
    return Broker(id=id, host=faker.hostname(), port=faker.port_number())


def random_brokers(nb_elements=10, variable_nb_elements=True):
    id_list = faker.pylist(
        nb_elements=nb_elements,
        variable_nb_elements=variable_nb_elements,
        value_types=int,
    )
    return [random_broker(id) for id in id_list]


def random_group(id=faker.pystr()):
    return Group(
        id=id,
        broker=random_broker(),
        state=faker.random.choice(["stable", "empty"]),
        members=faker.pyint(),
    )


def random_groups(nb_elements=10, variable_nb_elements=True):
    id_list = faker.pylist(
        nb_elements=nb_elements,
        variable_nb_elements=variable_nb_elements,
        value_types=str,
    )
    return [random_group(id) for id in id_list]


def random_partition(id=faker.pyint()):
    return Partition(
        id=id,
        leader=faker.pyint(),
        replicas=faker.pylist(value_types=int),
        isrs=faker.pylist(value_types=int),
    )


def random_partitions(nb_elements=10, variable_nb_elements=True):
    id_list = faker.pylist(
        nb_elements=nb_elements,
        variable_nb_elements=variable_nb_elements,
        value_types=int,
    )
    return [random_partition(id) for id in id_list]


def random_topic(name=faker.pystr()):
    return Topic(name=name, partitions=random_partitions(), groups=random_groups())


def random_topics(nb_elements=10, variable_nb_elements=True):
    id_list = faker.pylist(
        nb_elements=nb_elements,
        variable_nb_elements=variable_nb_elements,
        value_types=str,
    )
    return [random_topic(id) for id in id_list]


def random_cluster():
    return Cluster(
        brokers=random_brokers(),
        topics=random_topics(),
        version=faker.bothify("#.#.#"),
        has_schemas=faker.pybool(),
        protocol=faker.random.choice(["plain", "ssl"]),
    )


def random_broker_metadata():
    broker_metadata = BrokerMetadata()
    broker_metadata.id = faker.pyint()
    broker_metadata.host = faker.hostname()
    broker_metadata.port = faker.port_number()
    return broker_metadata


def random_group_member_metadata():
    group_member = GroupMember()
    group_member.id = faker.pystr()
    group_member.client_host = faker.hostname()
    group_member.client_id = faker.pystr()
    return group_member


def random_group_metadata():
    group_metadata = ConsumerGroupDescription(
        faker.pystr(),
        True,
        [random_group_member_metadata() for _ in range(faker.pyint(max_value=10))],
        faker.pystr(),
        faker.random.choice(["Stable", "Empty"]),
        Node(faker.pyint(), faker.pystr(), faker.pyint(), faker.pystr()),
    )
    return group_metadata


def random_topic_partition_metadata():
    topic_partition = TopicPartition(faker.pystr(), faker.pyint())
    topic_partition.offset = faker.pyint()
    return topic_partition


def random_partition_metadata():
    partition_metadata = PartitionMetadata()
    partition_metadata.id = faker.pyint()
    partition_metadata.leader = faker.pyint()
    partition_metadata.replicas = (faker.pylist(value_types=int),)
    partition_metadata.isrs = faker.pylist(value_types=int)
    return partition_metadata


def random_topic_metadata():
    topic_metadata = TopicMetadata()
    topic_metadata.topic = faker.pystr()
    topic_metadata.partitions = {
        i: random_partition_metadata() for i in range(faker.pyint(max_value=10))
    }
    return topic_metadata
