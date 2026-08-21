import json
import unittest
from pathlib import Path

import collect_spatial_evidence as CSE


ROOT = Path(__file__).resolve().parents[1]


class SpatialEvidenceTests(unittest.TestCase):
    def test_offline_spatial_evidence_validation_passes(self):
        result = CSE.validate(ROOT, ROOT / "groundtruth_geo.jsonl", ROOT / "spatial_evidence" / "records")
        self.assertEqual(result["status"], "passed", result["errors"])
        self.assertEqual(result["cases"], 33)

    def test_candidate_radius_exceeds_perturbation_plus_decision_radius(self):
        available = CSE.EPA_CANDIDATE_RADIUS_MILES * 1609.344
        required = 100.0 + 0.25 * 1609.344
        self.assertGreater(available, required)

    def test_polygon_capture_envelope_exceeds_test_matrix(self):
        self.assertGreater(CSE.CAPTURE_RADIUS_METERS, 100.0)

    def test_polygon_generalization_is_sub_decimeter(self):
        self.assertLessEqual(CSE.MAX_POLYGON_OFFSET_DEGREES * 111_320.0, 0.06)


if __name__ == "__main__":
    unittest.main()
