from unittest import TestCase

from kaskade.renderables.cluster_info import ClusterInfo
from tests.kafka import random_cluster


class TestKafkaInfo(TestCase):
    def test_string(self):
        cluster = random_cluster()
        expected = str(cluster)
        actual = str(ClusterInfo(cluster))

        self.assertEqual(expected, actual)

    def test_render_kafka_info_in_a_table(self):
        cluster = random_cluster()
        cluster_info = ClusterInfo(cluster)

        actual = cluster_info.__rich__()

        cells_label = actual.columns[0].cells
        cells_values = actual.columns[1].cells

        self.assertEqual("kafka:", next(cells_label))
        self.assertEqual(cluster.version, next(cells_values))

        self.assertEqual("brokers:", next(cells_label))
        self.assertEqual(str(cluster.brokers_count()), next(cells_values))

        self.assertEqual("schemas:", next(cells_label))
        self.assertEqual("yes" if cluster.has_schemas else "no", next(cells_values))

        self.assertEqual("protocol:", next(cells_label))
        self.assertEqual(cluster.protocol, next(cells_values))

    def test_render_kafka_default_protocol(self):
        cluster = random_cluster()
        cluster_info = ClusterInfo(cluster)
        cluster.protocol = None

        actual = cluster_info.__rich__()

        cells_values = list(actual.columns[1].cells)

        self.assertEqual("plain", cells_values[3])
