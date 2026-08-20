import json
import unittest
from pathlib import Path

import refresh_evidence


ROOT = Path(__file__).resolve().parents[1]


class EvidenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = refresh_evidence.load_rows()
        cls.by_id = {row["id"]: row for row in cls.rows}

    def test_all_public_evidence_validates_offline(self):
        result = refresh_evidence.validate(self.rows)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["items"], 33)
        self.assertEqual(result["addresses"], 11)

    def test_task_meanings_are_explicit(self):
        cleanup = [row for row in self.rows if row["task"] == "contamination_nearby"]
        self.assertTrue(all(row["answer"]["radius_miles"] == 0.25 for row in cleanup))
        self.assertTrue(all(row["answer"]["programs"] == ["Brownfields", "Superfund"] for row in cleanup))

    def test_acton_structure_is_not_scored_as_a_district(self):
        row = self.by_id["gtg-676366fd1083"]
        self.assertFalse(row["answer"]["in_historic_district"])
        evidence = json.loads((ROOT / row["evidence_path"]).read_text())
        excluded = evidence["derivation_rule"]["excluded_intersections"]
        self.assertTrue(any(record.get("RESNAME") == "Davis, Isaac, Trail" and record.get("ResType") == "structure" for record in excluded))

    def test_dc_answer_names_actual_districts_not_the_statuary_object(self):
        row = self.by_id["gtg-d5f5fad520ca"]
        self.assertTrue(row["answer"]["in_historic_district"])
        self.assertIn("Lafayette Square Historic District", row["answer"]["districts"])
        self.assertNotIn("American Revolution Statuary", row["answer"]["districts"])

    def test_chicago_stale_cleanup_positive_was_removed(self):
        row = self.by_id["gtg-1cf14a0cbce1"]
        self.assertFalse(row["answer"]["has_nearby_site"])
        self.assertEqual(row["answer"]["count"], 0)

    def test_no_permit_task_or_claim(self):
        serialized = json.dumps(self.rows).lower()
        self.assertNotIn("permit", serialized)


if __name__ == "__main__":
    unittest.main()
