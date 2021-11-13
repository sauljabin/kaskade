from unittest import TestCase

from rich.text import Text

from kaskade.renderables.scrollable_list import ScrollableList
from kaskade.unicodes import RIGHT_TRIANGLE
from tests import faker


class TestScrollableList(TestCase):
    def test_string(self):
        items = faker.pylist(
            nb_elements=10, variable_nb_elements=False, value_types=str
        )
        expected = str(items)
        actual = str(ScrollableList(items))

        self.assertEqual(expected, actual)

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

    def test_set_valid_selected(self):
        items = faker.pylist(
            nb_elements=10, variable_nb_elements=False, value_types=str
        )

        expected = items[5]

        scrollable = ScrollableList(items, max_len=3, selected=expected)
        actual = scrollable.renderables()

        self.assertListEqual([items[3], items[4], items[5]], actual)
        self.assertEqual(expected, scrollable.selected)

    def test_reset_is_selected_is_invalid(self):
        items = faker.pylist(
            nb_elements=10, variable_nb_elements=False, value_types=str
        )

        scrollable = ScrollableList(items, max_len=3)
        scrollable.selected = None

        self.assertIsNone(scrollable.selected)
        self.assertEquals(-1, scrollable.pointer)

        scrollable.selected = faker.word()

        self.assertIsNone(scrollable.selected)
        self.assertEquals(-1, scrollable.pointer)

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
