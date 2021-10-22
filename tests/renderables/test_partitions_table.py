from unittest import TestCase
from unittest.mock import MagicMock, call

from confluent_kafka.admin import PartitionMetadata

from kaskade.renderables.partitions_table import PartitionsTable
from tests import faker


class TestPartitionsTable(TestCase):
    def test_render_rows(self):
        partition = PartitionMetadata()
        partition.id = faker.pyint()
        partition.leader = faker.pyint()
        partition.replicas = faker.pylist(value_types=int)

        mock_table = MagicMock()

        table = PartitionsTable([partition])

        table.render_rows(mock_table, [partition])

        mock_table.add_row.assert_called_with(
            str(partition.id),
            str(partition.leader),
            str(partition.replicas),
            str(partition.isrs),
        )

    def test_get_renderables(self):
        partitions = faker.pylist(nb_elements=10, variable_nb_elements=False)

        table = PartitionsTable(partitions)

        renderables = table.renderables(3, 8)

        self.assertListEqual(partitions[3:8], renderables)

    def test_render_columns(self):
        table = PartitionsTable([])
        mock_table = MagicMock()

        table.render_columns(mock_table)

        calls = [
            call("id", header_style="bright_magenta bold", ratio=10),
            call("leader", header_style="bright_magenta bold", ratio=10),
            call("replicas", header_style="bright_magenta bold", ratio=40),
            call("in sync", header_style="bright_magenta bold", ratio=40),
        ]

        mock_table.add_column.assert_has_calls(calls)
