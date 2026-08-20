import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("replicated_review", ROOT / "replicated_review.py")
assert SPEC and SPEC.loader
RR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RR)


def load_first(task):
    cases = [json.loads(line) for line in (ROOT / "groundtruth_geo.jsonl").read_text().splitlines() if line]
    case = next(case for case in cases if case["task"] == task)
    receipt = json.loads((ROOT / case["evidence_path"]).read_text())
    return case, receipt


class ReplicatedReviewTests(unittest.TestCase):
    def test_gold_blind_second_implementation_passes_each_task(self):
        now = RR.parse_utc("2026-08-21T00:00:00Z")
        for task in RR.TASK_HOSTS:
            with self.subTest(task=task):
                case, receipt = load_first(task)
                result = RR.review_case(case, receipt, now)
                self.assertEqual(result["status"], "passed", result["issues"])
                self.assertEqual(result["derived_answer"], case["answer"])
                self.assertIs(result["gold_hidden_during_derivation"], True)

    def test_wrong_answer_is_detected_after_derivation(self):
        case, receipt = load_first("fema_sfha")
        case = copy.deepcopy(case)
        case["answer"] = RR.flipped_answer(case["task"], case["answer"])
        result = RR.review_case(case, receipt, RR.parse_utc("2026-08-21T00:00:00Z"))
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("derived_answer_disagrees", codes)

    def test_rehashed_wrong_source_is_detected_semantically(self):
        case, receipt = load_first("historic_district")
        case, receipt = copy.deepcopy(case), copy.deepcopy(receipt)
        receipt["official_queries"][0]["record_url"] = "https://example.com/query?geometry=0%2C0"
        RR.rehash_case(case, receipt)
        result = RR.review_case(case, receipt, RR.parse_utc("2026-08-21T00:00:00Z"))
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("official_source_host_not_allowed", codes)

    def test_service_error_cannot_be_recast_as_no(self):
        case, receipt = load_first("fema_sfha")
        name, mutated_case, mutated_receipt = next(
            variant for variant in RR.adversarial_variants(case, receipt) if variant[0] == "unknown_forced_to_no"
        )
        self.assertEqual(name, "unknown_forced_to_no")
        result = RR.review_case(mutated_case, mutated_receipt, RR.parse_utc("2026-08-21T00:00:00Z"))
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("official_source_error", codes)
        self.assertIn("answer_unresolved", codes)

    def test_adversarial_suite_detects_every_mutation_on_sample(self):
        loaded = [load_first(task) for task in RR.TASK_HOSTS]
        result = RR.run_adversarial(loaded, RR.parse_utc("2026-08-21T00:00:00Z"))
        self.assertEqual(result["attempted"], 24)
        self.assertEqual(result["detected"], result["attempted"], result)


if __name__ == "__main__":
    unittest.main()
