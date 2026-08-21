import ast
import copy
import json
import unittest
from pathlib import Path

import geospatial_review as GR
from shapely.geometry import Point, box, mapping


ROOT = Path(__file__).resolve().parents[1]


class GeospatialReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = [json.loads(line) for line in (ROOT / "groundtruth_geo.jsonl").read_text().splitlines() if line]

    def test_third_engine_imports_neither_existing_derivation(self):
        tree = ast.parse((ROOT / "geospatial_review.py").read_text())
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertNotIn("refresh_evidence", imported)
        self.assertNotIn("replicated_review", imported)

    def test_esri_even_odd_fill_preserves_hole_when_orientation_reverses(self):
        shell = [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]
        hole = [[3, 3], [7, 3], [7, 7], [3, 7], [3, 3]]
        clip = box(-1, -1, 11, 11)
        first, _ = GR.esri_polygon({"rings": [shell, hole]}, clip)
        second, _ = GR.esri_polygon({"rings": [list(reversed(shell)), list(reversed(hole))]}, clip)
        self.assertTrue(first.equals(second))
        self.assertTrue(first.covers(Point(1, 1)))
        self.assertFalse(first.covers(Point(5, 5)))

    def test_boundary_contact_is_included(self):
        polygon, _ = GR.esri_polygon(
            {"rings": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}, box(-1, -1, 2, 2)
        )
        self.assertTrue(polygon.covers(Point(0, 0.5)))
        self.assertFalse(polygon.contains(Point(0, 0.5)))

    def test_matrix_has_one_center_and_56_displacements(self):
        points = GR.perturbation_points(-70.0, 42.0)
        self.assertEqual(len(points), 57)
        self.assertEqual(sum(point["radius_meters"] == 0 for point in points), 1)
        self.assertEqual({point["radius_meters"] for point in points}, set(GR.RADII_METERS))

    def test_boundary_contact_preserves_overlapping_sensitivity_flag(self):
        primary, flags = GR.perturbation_labels(0.01, changed_count=1, unresolved_count=0, center_error=None)
        self.assertEqual(primary, "boundary_contact")
        self.assertEqual(flags, ["boundary_contact", "sensitive"])

    def test_unavailable_has_highest_precedence(self):
        primary, flags = GR.perturbation_labels(0.0, changed_count=1, unresolved_count=1, center_error="bad geometry")
        self.assertEqual(primary, "geometry_unavailable")
        self.assertEqual(flags, ["geometry_unavailable"])

    def test_epa_threshold_is_inclusive_and_geodesic(self):
        lon, lat = -70.0, 42.0
        site_lon, site_lat, _ = GR.GEOD.fwd(lon, lat, 90, GR.EPA_THRESHOLD_METERS)
        feature = {
            "source": "EPA Envirofacts Superfund",
            "attributes": {"registry_id": "r", "site_id": "s"},
            "geometry": Point(site_lon, site_lat),
            "key": ("Superfund", "r", "s"),
        }
        answer, error = GR.derive("contamination_nearby", lon, lat, [feature])
        self.assertIsNone(error)
        self.assertEqual(answer["count"], 1)

    def test_public_center_answers_pass_third_engine(self):
        report = GR.run(ROOT, ROOT / "groundtruth_geo.jsonl", ROOT / "spatial_evidence" / "records")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["summary"]["passed_cases"], 33)
        self.assertEqual(report["summary"]["perturbation_samples"], 1881)
        self.assertGreater(report["summary"]["perturbation_classes"].get("sensitive", 0), 0)

    def test_corrupt_polygon_fails_closed(self):
        row = next(item for item in self.rows if item["task"] == "fema_sfha")
        record = json.loads((ROOT / "spatial_evidence" / "records" / f"{row['id']}.json").read_text())
        record = copy.deepcopy(record)
        record["captures"][0]["raw_response"]["features"][0]["geometry"]["rings"][0][0][0] = "not-a-number"
        record["captures"][0]["response_sha256"] = GR.sha256(record["captures"][0]["raw_response"])
        result = GR.review_case(row, record)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["perturbation_class"], "geometry_unavailable")


if __name__ == "__main__":
    unittest.main()
