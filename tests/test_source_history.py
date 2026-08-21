import copy
import json
import tempfile
import unittest
from pathlib import Path

import source_history as SH


ROOT = Path(__file__).resolve().parents[1]


class SourceHistoryTests(unittest.TestCase):
    def baseline(self):
        return {
            "case_id": "case-1",
            "task": "fema_sfha",
            "available": True,
            "answer_sha256": "answer-1",
            "identity_semantic_sha256": "identity-1",
            "official_records_sha256": "records-1",
            "spatial_attributes_sha256": "spatial-1",
            "geometry_sha256": "geometry-1",
            "raw_evidence_sha256": "raw-1",
            "raw_spatial_evidence_sha256": "spatial-raw-1",
        }

    def test_synthetic_corpus_covers_each_semantic_change_class(self):
        corpus = json.loads((ROOT / "tests" / "fixtures" / "source_change_corpus.json").read_text())
        for fixture in corpus["cases"]:
            with self.subTest(name=fixture["name"]):
                before = self.baseline()
                after = copy.deepcopy(before)
                after.update(fixture["changes"])
                self.assertEqual(SH.classify_case_change(before, after), fixture["expected"])

    def test_classification_change_has_precedence_over_raw_churn(self):
        before = self.baseline()
        after = copy.deepcopy(before)
        after["answer_sha256"] = "answer-2"
        after["raw_evidence_sha256"] = "raw-2"
        self.assertEqual(SH.classify_case_change(before, after), "classification_change")

    def test_schema_change_is_distinct_from_metadata_churn(self):
        before = {"source_id": "x", "schema_sha256": "s1", "raw_metadata_sha256": "r1"}
        after = {"source_id": "x", "schema_sha256": "s2", "raw_metadata_sha256": "r2"}
        self.assertEqual(SH.classify_metadata_change(before, after), "schema_change")

    def test_snapshot_content_hash_validates(self):
        manifest = SH.build_snapshot(
            ROOT,
            ROOT / "groundtruth_geo.jsonl",
            ROOT / "spatial_evidence" / "records",
            ROOT / "history" / "snapshots",
            "9999-12-31",
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "manifest.json"
            path.write_bytes(SH.canonical_json(manifest) + b"\n")
            self.assertEqual(SH.validate_manifest(path, ROOT), [])


if __name__ == "__main__":
    unittest.main()
