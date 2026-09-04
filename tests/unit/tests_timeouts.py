import unittest

from kaskade.timeouts import TimeoutConfig


class TestTimeoutConfig(unittest.TestCase):
    def test_defaults(self) -> None:
        self.assertEqual(
            {
                "consumer.poll": 0.5,
                "consumer.idle": 2.5,
                "consumer.assignment": 15.0,
                "consumer.request": 10.0,
                "admin.read": 10.0,
                "admin.write": 60.0,
            },
            TimeoutConfig().as_dict(),
        )

    def test_parses_partial_configuration(self) -> None:
        config = TimeoutConfig.from_dict({"consumer.request": "20", "admin.read": "12.5"})

        self.assertEqual(20.0, config.consumer_request)
        self.assertEqual(12.5, config.admin_read)
        self.assertEqual(0.5, config.consumer_poll)

    def test_rejects_unknown_properties(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unrecognized timeout properties: unknown"):
            TimeoutConfig.from_dict({"unknown": "10"})

    def test_rejects_non_numeric_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "consumer.poll must be a number of seconds"):
            TimeoutConfig.from_dict({"consumer.poll": "fast"})

    def test_rejects_non_positive_and_non_finite_values(self) -> None:
        for value in ("0", "-1", "nan", "inf"):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "must be greater than zero"),
            ):
                TimeoutConfig.from_dict({"admin.read": value})


if __name__ == "__main__":
    unittest.main()
