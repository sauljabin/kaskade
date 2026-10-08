import tempfile
import unittest
from pathlib import Path

from kaskade.producer.source import DraftField, RecordDraft, SourceError, load_drafts


class TestLoadDrafts(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def write(self, name: str, text: str) -> Path:
        path = self.directory / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_json_loads_one_record_with_ordered_headers_and_nulls(self):
        path = self.write(
            "record.json",
            '{"headers": [{"key": "a", "value": "1"}, {"key": "a", "value": null},'
            ' {"key": "b", "value": ""}], "key": {"content": ""},'
            ' "value": {"content": {"status": "paid"}}}',
        )

        drafts = load_drafts(path)

        self.assertEqual(
            (
                RecordDraft(
                    headers=(("a", "1"), ("a", None), ("b", "")),
                    key=DraftField("", is_null=False),
                    value=DraftField({"status": "paid"}, is_null=False),
                ),
            ),
            drafts,
        )

    def test_jsonl_loads_every_line_and_skips_blank_lines(self):
        text = '{"key": {"content": "1"}}\n\n{"value": {"content": null}}\n{}\n'
        path = self.write("records.jsonl", text)

        drafts = load_drafts(path)

        self.assertEqual(3, len(drafts))
        self.assertEqual(DraftField("1", is_null=False), drafts[0].key)
        self.assertEqual(DraftField(), drafts[1].value)
        self.assertEqual(RecordDraft(), drafts[2])
        self.assertEqual(text, path.read_text(encoding="utf-8"))

    def test_invalid_documents_name_their_line(self):
        cases = (
            ("a.jsonl", '{}\n\n{"key": "x"}\n', "Line 3: 'key' must be an object"),
            ("b.jsonl", "{}\n{oops\n", "Line 2: invalid JSON"),
            ("c.jsonl", '{"extra": 1}\n', "Line 1: unknown record field"),
            ("d.json", '{\n  "headers": [\n  {"key": 1, "value": null}]\n}', "Line 1: header 0"),
            ("e.json", '{\n  "key": {"content": 1,}\n}', "Line 2: invalid JSON"),
            ("f.jsonl", '{"key": {"content": 1, "format": "x"}}', "unknown 'key' field"),
            ("g.jsonl", "\n\n", "contains no records"),
        )
        for name, text, message in cases:
            with self.subTest(name=name), self.assertRaisesRegex(SourceError, message):
                load_drafts(self.write(name, text))

    def test_rejects_other_extensions(self):
        with self.assertRaisesRegex(SourceError, r"\.json or \.jsonl"):
            load_drafts(self.write("records.yaml", "{}"))


if __name__ == "__main__":
    unittest.main()
