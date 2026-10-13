import tempfile
import unittest
from pathlib import Path

from kaskade.producer.source import DraftField, RecordDraft, SourceError, load_draft


class TestLoadDraft(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def write(self, name: str, text: str) -> Path:
        path = self.directory / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_loads_one_record_with_ordered_headers_and_nulls(self):
        text = (
            '{"headers": [{"key": "a", "value": "1"}, {"key": "a", "value": null},'
            ' {"key": "b", "value": ""}], "key": {"content": ""},'
            ' "value": {"content": {"status": "paid"}}}'
        )
        path = self.write("record.json", text)

        draft = load_draft(path)

        self.assertEqual(
            RecordDraft(
                headers=(("a", "1"), ("a", None), ("b", "")),
                key=DraftField("", is_null=False),
                value=DraftField({"status": "paid"}, is_null=False),
            ),
            draft,
        )
        self.assertEqual(text, path.read_text(encoding="utf-8"))

    def test_missing_and_null_content_are_null(self):
        draft = load_draft(self.write("record.json", '{"value": {"content": null}}'))

        self.assertEqual(RecordDraft(), draft)

    def test_rejects_invalid_documents(self):
        cases = (
            ('{"key": "x"}', "'key' must be an object"),
            ('{\n  "key": {"content": 1,}\n}', "Invalid JSON at line 2"),
            ('{"extra": 1}', "unknown record field"),
            ('{"headers": [{"key": 1, "value": null}]}', "header 0"),
            ('{"key": {"content": 1, "format": "x"}}', "unknown 'key' field"),
            ("[{}, {}]", "must be a JSON object"),
        )
        for text, message in cases:
            with self.subTest(text=text), self.assertRaisesRegex(SourceError, message):
                load_draft(self.write("record.json", text))


if __name__ == "__main__":
    unittest.main()
