import unittest

from shapely.geometry import Point, mapping, box

import collect_property_support as CPS
import geospatial_review as GR
import property_support_review as PSR


class PropertySupportTests(unittest.TestCase):
    def test_stored_public_support_receipts_are_hash_consistent(self):
        root = CPS.ROOT
        records = {}
        for path in sorted((root / "property_support" / "records").glob("*.json")):
            record = __import__("json").loads(path.read_text())
            records.update({case_id: record for case_id in record["case_ids"]})
            for capture in record["captures"]:
                self.assertEqual(GR.sha256(capture["raw_response"]), capture["response_sha256"])
        for path in sorted((root / "property_support" / "spatial_records").glob("*.json")):
            record = __import__("json").loads(path.read_text())
            self.assertEqual(GR.sha256(records[record["case_id"]]), record["property_support_sha256"])
            for capture in record["captures"]:
                self.assertEqual(GR.sha256(capture["raw_response"]), capture["response_sha256"])

    def test_exact_addressed_building_is_selected(self):
        address = {
            "role": "address_point",
            "feature_count": 1,
            "response_sha256": "address",
            "raw_response": {
                "features": [{"geometry": {"type": "Point", "coordinates": [-71.0, 42.0]}}]
            },
        }
        building = {
            "role": "building",
            "feature_count": 1,
            "response_sha256": "building",
            "raw_response": {
                "features": [
                    {
                        "properties": {"FULLADDRESS": "1 Main St"},
                        "geometry": mapping(box(-71.001, 41.999, -70.999, 42.001)),
                    }
                ]
            },
        }
        config = {
            "building_query": {"address_field": "FULLADDRESS", "expected_address": "1 Main St"}
        }
        support, issues = CPS.select_support(config, [address, building], (-71.002, 42.0))
        self.assertEqual(issues, [])
        self.assertEqual(support["kind"], "official_building_footprint")
        self.assertEqual(support["confidence_tier"], "A")

    def test_address_outside_building_fails_closed(self):
        address = {
            "role": "address_point",
            "feature_count": 1,
            "response_sha256": "address",
            "raw_response": {
                "features": [{"geometry": {"type": "Point", "coordinates": [-71.0, 42.0]}}]
            },
        }
        building = {
            "role": "building",
            "feature_count": 1,
            "response_sha256": "building",
            "raw_response": {
                "features": [
                    {
                        "properties": {"FULLADDRESS": "1 Main St"},
                        "geometry": mapping(box(-72.001, 41.999, -71.999, 42.001)),
                    }
                ]
            },
        }
        config = {
            "building_query": {"address_field": "FULLADDRESS", "expected_address": "1 Main St"}
        }
        support, issues = CPS.select_support(config, [address, building], (-71.0, 42.0))
        self.assertIsNone(support)
        self.assertIn("official address point is not inside the selected official building", issues)

    def test_fema_boundary_across_building_is_mixed(self):
        support = box(-71.001, 41.999, -70.999, 42.001)
        features = [
            {
                "attributes": {"SFHA_TF": "T", "FLD_ZONE": "AE"},
                "geometry": box(-71.001, 41.999, -71.0, 42.001),
                "key": ("a",),
            },
            {
                "attributes": {"SFHA_TF": "F", "FLD_ZONE": "X"},
                "geometry": box(-71.0, 41.999, -70.999, 42.001),
                "key": ("b",),
            },
        ]
        result = PSR.fema_relation(support, features)
        self.assertEqual(result["classification"], "mixed")

    def test_conflicting_overlapping_fema_attributes_are_mixed(self):
        support = box(-71.001, 41.999, -70.999, 42.001)
        features = [
            {
                "attributes": {"SFHA_TF": "T", "FLD_ZONE": "AE"},
                "geometry": support,
                "key": ("a",),
            },
            {
                "attributes": {"SFHA_TF": "F", "FLD_ZONE": "X"},
                "geometry": box(-71.001, 41.999, -71.0, 42.001),
                "key": ("b",),
            },
        ]
        self.assertEqual(PSR.fema_relation(support, features)["classification"], "mixed")

    def test_historic_partial_overlap_is_mixed(self):
        support = box(-71.001, 41.999, -70.999, 42.001)
        feature = {
            "attributes": {"ResType": "district", "STATUS": "Listed", "RESNAME": "Example"},
            "geometry": box(-71.001, 41.999, -71.0, 42.001),
            "key": ("d",),
        }
        result = PSR.historic_relation(support, [feature])
        self.assertEqual(result["classification"], "mixed")
        self.assertAlmostEqual(result["districts"][0]["support_area_percent"], 50.0, places=2)

    def test_contamination_relation_distinguishes_yes_no_and_mixed(self):
        support = box(-71.0001, 41.9999, -70.9999, 42.0001)
        near = {"geometry": Point(-71.0, 42.0), "key": ("near",)}
        far = {"geometry": Point(-72.0, 43.0), "key": ("far",)}
        edge = {"geometry": Point(-70.9952, 42.0), "key": ("edge",)}
        self.assertEqual(PSR.contamination_relation(support, [near])["classification"], "certain_yes")
        self.assertEqual(PSR.contamination_relation(support, [far])["classification"], "certain_no")
        self.assertEqual(PSR.contamination_relation(support, [edge])["classification"], "mixed")


if __name__ == "__main__":
    unittest.main()
