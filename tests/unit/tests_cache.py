import unittest

from kaskade.cache import LruCache


class TestLruCache(unittest.TestCase):
    def test_evicts_the_least_recently_used_entry(self) -> None:
        cache: LruCache[str, int] = LruCache(2)
        cache.put("orders", 1)
        cache.put("payments", 2)

        self.assertEqual(1, cache.get("orders"))
        cache.put("users", 3)

        self.assertEqual(2, len(cache))
        self.assertIn("orders", cache)
        self.assertNotIn("payments", cache)
        self.assertIsNone(cache.get("payments"))

    def test_replacing_an_entry_marks_it_recent(self) -> None:
        cache: LruCache[str, int] = LruCache(2)
        cache.put("orders", 1)
        cache.put("payments", 2)
        cache.put("orders", 3)
        cache.put("users", 4)

        self.assertEqual(3, cache.get("orders"))
        self.assertNotIn("payments", cache)

    def test_remove_ignores_missing_entries(self) -> None:
        cache: LruCache[str, int] = LruCache(1)
        cache.put("orders", 1)

        cache.remove("orders")
        cache.remove("orders")

        self.assertEqual(0, len(cache))
