import unittest

from kaskade.deserializers import StringDeserializer
from tests import faker


class TestDeserializer(unittest.TestCase):

    def test_deserialization(self):
        expected_value = faker.word()
        deserializer = StringDeserializer()

        result = deserializer.deserialize(expected_value.encode("utf-8"))

        self.assertEqual(expected_value, result)
        self.fail()
