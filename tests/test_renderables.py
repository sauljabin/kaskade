from unittest import TestCase
from unittest.mock import MagicMock, call, patch

from pyfiglet import Figlet
from rich.text import Text

from kaskade.renderables.kafka_info import KafkaInfo
from kaskade.renderables.kaskade_name import KaskadeName
from kaskade.renderables.kaskade_version import KaskadeVersion
from kaskade.renderables.scrollable_list import ScrollableList
from kaskade.renderables.shortcuts import Shortcuts
from kaskade.unicodes import RIGHT_TRIANGLE
from tests import faker

version = faker.bothify("#.#.#")


class TestKaskadeVersion(TestCase):
    @patch("kaskade.renderables.kaskade_version.VERSION", version)
    def test_version(self):
        expected_value = "kaskade v" + version

        actual = str(KaskadeVersion())

        self.assertEqual(expected_value, actual)

    @patch("kaskade.renderables.kaskade_version.VERSION", version)
    def test_rich_version(self):
        expected_value = "kaskade v" + version

        rich = KaskadeVersion().__rich__()
        actual = rich.plain

        self.assertIsInstance(rich, Text)
        self.assertEqual(expected_value, actual)


class TestKaskadeName(TestCase):
    def test_rich_name(self):
        figlet = Figlet(font="standard")
        expected = figlet.renderText("kaskade")

        rich = KaskadeName().__rich__()
        actual = rich.plain

        self.assertIn(actual, expected)

    def test_name(self):
        figlet = Figlet(font="standard")
        expected = figlet.renderText("kaskade").rstrip()

        actual = str(KaskadeName())

        self.assertEqual(expected, actual)


class TestShortcuts(TestCase):
    @patch("kaskade.renderables.shortcuts.Table")
    def test_render_shortcuts_in_a_table(self, mock_class_table):
        mock_table = MagicMock()
        mock_class_table.return_value = mock_table

        shortcuts = Shortcuts()
        actual = shortcuts.__rich__()

        self.assertEqual(mock_table, actual)
        mock_class_table.assert_called_with(box=None, expand=False)
        mock_table.add_column.assert_has_calls(
            [call(style="magenta bold"), call(style="yellow bold")]
        )

        mock_table.add_row.assert_has_calls(
            [
                call("quit:", "q"),
                call("refresh:", "f5"),
                call("navigate:", "\u2190 \u2192 \u2191 \u2193"),
            ]
        )

    def test_string(self):
        expected = str(
            {
                "quit": "q",
                "refresh": "f5",
                "navigate": "\u2190 \u2192 \u2191 \u2193",
            }
        )
        actual = str(Shortcuts())

        self.assertEqual(expected, actual)


class TestKafkaInfo(TestCase):
    @patch("kaskade.renderables.kafka_info.Table")
    def test_render_kafka_info_in_a_table(self, mock_class_table):
        mock_table = MagicMock()
        mock_class_table.return_value = mock_table

        kafka_version = faker.bothify("#.#")
        total_brokers = faker.pyint()
        has_schemas = True
        protocol = faker.word().upper()

        kafka_info = KafkaInfo(
            kafka_version=kafka_version,
            total_brokers=total_brokers,
            has_schemas=has_schemas,
            protocol=protocol,
        )

        actual = kafka_info.__rich__()

        self.assertEqual(mock_table, actual)
        mock_class_table.assert_called_with(box=None, expand=False)
        mock_table.add_column.assert_has_calls([call(style="bold blue"), call()])

        mock_table.add_row.assert_has_calls(
            [
                call("kafka:", kafka_version),
                call("brokers:", str(total_brokers)),
                call("schemas:", "yes"),
                call("protocol:", protocol.lower()),
            ]
        )

    @patch("kaskade.renderables.kafka_info.Table")
    def test_render_kafka_info_in_a_table_and_print_no_if_schames_is_false(
        self, mock_class_table
    ):
        mock_table = MagicMock()
        mock_class_table.return_value = mock_table

        has_schemas = False

        kafka_info = KafkaInfo(
            has_schemas=has_schemas,
        )

        kafka_info.__rich__()

        mock_table.add_row.assert_has_calls(
            [
                call("schemas:", "no"),
            ]
        )


class TestScrollableList(TestCase):
    def test_renderables(self):
        items = faker.pylist(
            nb_elements=10, variable_nb_elements=False, value_types=str
        )

        scrollable = ScrollableList(items, max_len=3)
        actual = scrollable.renderables()

        self.assertListEqual([items[0], items[1], items[2]], actual)

    def test_set_pointer_is_a_valid_pointer(self):
        items = faker.pylist(
            nb_elements=10, variable_nb_elements=False, value_types=str
        )

        scrollable = ScrollableList(items, max_len=3, pointer=5)
        actual = scrollable.renderables()

        self.assertListEqual([items[3], items[4], items[5]], actual)
        self.assertEqual(items[5], scrollable.selected)

    def test_pointer_goes_to_end_if_is_negative(self):
        items = faker.pylist(
            nb_elements=10, variable_nb_elements=False, value_types=str
        )

        scrollable = ScrollableList(items, max_len=3)
        scrollable.next()
        scrollable.previous()
        actual = scrollable.renderables()

        self.assertListEqual([items[7], items[8], items[9]], actual)
        self.assertEqual(items[9], scrollable.selected)

    def test_pointer_starts_in_0(self):
        items = faker.pylist(
            nb_elements=10, variable_nb_elements=False, value_types=str
        )

        scrollable = ScrollableList(items, max_len=3)
        scrollable.next()
        actual = scrollable.renderables()

        self.assertListEqual([items[0], items[1], items[2]], actual)
        self.assertEqual(items[0], scrollable.selected)

    def test_renders_previous_items(self):
        items = faker.pylist(
            nb_elements=10, variable_nb_elements=False, value_types=str
        )

        scrollable = ScrollableList(items, max_len=2)
        scrollable.next()
        scrollable.next()
        scrollable.next()
        scrollable.next()
        scrollable.next()
        scrollable.previous()
        scrollable.previous()
        scrollable.previous()
        actual = scrollable.renderables()

        self.assertListEqual([items[1], items[2]], actual)
        self.assertEqual(items[1], scrollable.selected)

    def test_pointer_goes_to_start_if_is_bigger_then_list_size(self):
        items = faker.pylist(
            nb_elements=10, variable_nb_elements=False, value_types=str
        )

        scrollable = ScrollableList(items, max_len=3, pointer=8)
        scrollable.next()
        scrollable.next()
        actual = scrollable.renderables()

        self.assertListEqual([items[0], items[1], items[2]], actual)
        self.assertEqual(items[0], scrollable.selected)

    def test_renderables_with_multiples_next(self):
        items = faker.pylist(
            nb_elements=10, variable_nb_elements=False, value_types=str
        )

        scrollable = ScrollableList(items, max_len=2)
        scrollable.next()
        scrollable.next()
        scrollable.next()
        actual = scrollable.renderables()

        self.assertListEqual([items[1], items[2]], actual)

    def test_renderables_with_multiples_next_and_previous(self):
        items = faker.pylist(
            nb_elements=10, variable_nb_elements=False, value_types=str
        )

        scrollable = ScrollableList(items, max_len=2)
        scrollable.next()
        scrollable.next()
        scrollable.next()
        scrollable.next()
        scrollable.previous()
        actual = scrollable.renderables()

        self.assertListEqual([items[2], items[3]], actual)
        self.assertEqual(items[2], scrollable.selected)

    def test_initialize_internal_list(self):
        scrollable = ScrollableList(None)
        self.assertListEqual([], scrollable.list)

    def test_max_len_is_list_len_if_not_initialize(self):
        items = faker.pylist()
        scrollable = ScrollableList(items)
        self.assertEqual(len(items), scrollable.max_len)

    def test_max_len_is_list_len_if_max_len_is_bigger_then_list_size(self):
        items = faker.pylist()
        scrollable = ScrollableList(items, max_len=len(items) + 10)
        self.assertEqual(len(items), scrollable.max_len)

    def test_reset(self):
        items = faker.pylist()
        scrollable = ScrollableList(items)

        scrollable.next()
        scrollable.reset()

        self.assertIsNone(scrollable.selected)
        self.assertEqual(-1, scrollable.pointer)
        self.assertEqual(0, scrollable.start_rendering)
        self.assertEqual(len(items), scrollable.end_rendering)

    def test_render_list(self):

        items = faker.pylist(
            nb_elements=10, variable_nb_elements=False, value_types=str
        )

        scrollable = ScrollableList(items, max_len=3)
        scrollable.next()
        scrollable.next()
        actual = scrollable.__rich__()

        self.assertIsInstance(actual, Text)
        self.assertEqual(
            f"  1 {items[0]}\n{RIGHT_TRIANGLE} 2 {items[1]}\n  3 {items[2]}\n",
            actual.plain,
        )
