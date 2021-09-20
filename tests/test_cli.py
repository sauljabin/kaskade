import unittest

from faker import Faker

from kaskade.cli import CliOptions

faker = Faker()


class TestCliOptions(unittest.TestCase):
    def test_options_to_attributes(self):
        dict_fake = faker.pydict(2)
        dict_fake["test"] = None

        cli_options = CliOptions(dict_fake)

        for key, value in dict_fake.items():
            self.assertEqual(getattr(cli_options, key), value)

        self.assertEqual(cli_options.test, None)
