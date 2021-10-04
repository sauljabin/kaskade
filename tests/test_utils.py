from unittest import TestCase

from kaskade.utils.circular_list import CircularList
from tests import faker

LIST_SIZE = 3


class TestCircularList(TestCase):
    def setUp(self):
        self.original_list = faker.pylist(
            nb_elements=LIST_SIZE, variable_nb_elements=False
        )
        self.circular_list = CircularList(self.original_list)

    def test_first_next_is_the_beginning(self):
        self.assertEqual(self.original_list[0], self.circular_list.next())

    def test_next(self):
        self.circular_list.next()
        self.assertEqual(self.original_list[1], self.circular_list.next())

    def test_next_using_next(self):
        iterator = self.circular_list
        next(iterator)
        self.assertEqual(self.original_list[1], next(iterator))

    def test_len(self):
        self.assertEqual(LIST_SIZE, len(self.circular_list))

    def test_previous(self):
        self.circular_list.next()
        self.circular_list.next()
        self.assertEqual(self.original_list[0], self.circular_list.previous())

    def test_next_is_the_first_if_reach_the_end_of_the_list(self):
        self.circular_list.next()
        self.circular_list.next()
        self.circular_list.next()
        self.assertEqual(self.original_list[0], self.circular_list.next())

    def test_previous_is_the_last_item_if_pointers_is_in_the_beginning(self):
        self.assertEqual(self.original_list[-1], self.circular_list.previous())
