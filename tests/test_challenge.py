import unittest

from challenge.common import validate_submission


class BlindChallengeTests(unittest.TestCase):
    def submission(self):
        return {
            "schema_version": "groundtruth_geo_blind_submission.v1",
            "participant": {
                "organization": "Example",
                "system_name": "System",
                "system_version": "1",
                "submitted_by": "Evaluator",
            },
            "predictions": [
                {
                    "item_id": "blind-one",
                    "attempted": False,
                    "answer": None,
                    "sources": [],
                }
            ],
        }

    def test_complete_abstention_is_schema_valid(self):
        self.assertEqual(validate_submission(self.submission(), {"blind-one"}), [])

    def test_missing_item_and_duplicate_are_rejected(self):
        document = self.submission()
        document["predictions"].append(dict(document["predictions"][0]))
        errors = validate_submission(document, {"blind-one", "blind-two"})
        self.assertTrue(any("duplicate item_id" in error for error in errors))
        self.assertTrue(any("missing 1" in error for error in errors))

    def test_attempted_null_answer_is_rejected(self):
        document = self.submission()
        document["predictions"][0]["attempted"] = True
        errors = validate_submission(document, {"blind-one"})
        self.assertIn("blind-one: an attempted answer must be boolean", errors)


if __name__ == "__main__":
    unittest.main()
