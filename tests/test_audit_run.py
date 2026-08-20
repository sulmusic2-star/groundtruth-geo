import copy
import json
import unittest

import audit_run
import refresh_evidence


class AuditRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.row = refresh_evidence.load_rows()[0]
        cls.evidence = json.loads((refresh_evidence.ROOT / cls.row["evidence_path"]).read_text())

    def accepted_prediction(self):
        key = refresh_evidence.TASK_KEYS[self.row["task"]]
        return {
            "attempted": True,
            "answer": self.row["answer"][key],
            "secondary_answer": None,
            "requested_address": self.row["address"],
            "matched_address": self.row["matched_address"],
            "longitude": self.row["longitude"],
            "latitude": self.row["latitude"],
            "sources": [
                {
                    "url": self.evidence["official_queries"][0]["record_url"],
                    "retrieved_at": self.row["retrieved_at"],
                    "record_id": "test",
                    "supports_answer": True,
                }
            ],
            "explanation": "test",
        }

    def test_fully_supported_prediction_is_accepted(self):
        result = audit_run.score_item(self.row, self.accepted_prediction())
        self.assertTrue(result["accepted"])
        self.assertFalse(result["failure_to_abstain"])

    def test_wrong_property_is_caught_even_when_boolean_is_lucky(self):
        prediction = self.accepted_prediction()
        prediction["matched_address"] = "999 WRONG ST"
        prediction["longitude"] = -100
        prediction["latitude"] = 30
        result = audit_run.score_item(self.row, prediction)
        self.assertTrue(result["wrong_property"])
        self.assertTrue(result["unsupported_answer"])
        self.assertTrue(result["failure_to_abstain"])

    def test_general_homepage_is_not_a_usable_citation(self):
        prediction = self.accepted_prediction()
        prediction["sources"][0]["url"] = "https://msc.fema.gov/portal/home"
        result = audit_run.score_item(self.row, prediction)
        self.assertFalse(result["wrong_source"])
        self.assertTrue(result["unusable_citation"])
        self.assertTrue(result["failure_to_abstain"])

    def test_wrong_boolean_is_unsupported(self):
        prediction = self.accepted_prediction()
        prediction["answer"] = not prediction["answer"]
        result = audit_run.score_item(self.row, prediction)
        self.assertTrue(result["unsupported_answer"])
        self.assertTrue(result["failure_to_abstain"])

    def test_undated_evidence_is_caught(self):
        prediction = self.accepted_prediction()
        prediction["sources"][0]["retrieved_at"] = None
        result = audit_run.score_item(self.row, prediction)
        self.assertTrue(result["stale_or_undated_evidence"])

    def test_abstention_avoids_error_but_is_not_accepted(self):
        prediction = self.accepted_prediction()
        prediction.update({"attempted": False, "answer": None, "sources": []})
        result = audit_run.score_item(self.row, prediction)
        self.assertTrue(result["abstained"])
        self.assertFalse(result["accepted"])
        self.assertFalse(result["failure_to_abstain"])


if __name__ == "__main__":
    unittest.main()
