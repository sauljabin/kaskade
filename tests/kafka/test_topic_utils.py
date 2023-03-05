from unittest import TestCase

from kaskade.kafka.topic_utils import validate_topic_name


class Test(TestCase):
    def test_validate_topic_name(self):
        topics = [
            "body-temp.events",
            "bpm.1",
            "crypto-sentiment_",
            "game-leaderboard-KSTREAM-AGGREGATE-STATE-STORE-0000000014-changelog",
            ".",
            "-",
            "_",
            "test#",
            "$",
            "%",
        ]
        expected = [True, True, True, True, True, True, True, False, False, False]

        results = [validate_topic_name(topic) for topic in topics]

        self.assertListEqual(expected, results)
