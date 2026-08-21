#!/usr/bin/env python3
"""Review sensitive cases over an official building or parcel, not one dot.

The result is deliberately set-valued.  ``certain_yes`` means every location
in the selected property support produces yes; ``certain_no`` means every
location produces no; ``mixed`` means the official condition crosses the
property support and a point answer would depend on where the point landed.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from shapely.geometry import Point, box, shape
from shapely.ops import transform as transform_geometry, unary_union

import geospatial_review as GR


ROOT = Path(__file__).resolve().parent
SUPPORT_DIR = ROOT / "property_support" / "records"
SPATIAL_DIR = ROOT / "property_support" / "spatial_records"
OUTPUT = ROOT / "proof" / "property-support-review-public-20260821.json"
EPA_THRESHOLD_METERS = 0.25 * 1609.344
# Sub-square-meter slivers can be introduced when separate WGS84 polygon edges
# are projected independently.  This tolerance is only for topology closure;
# reported intersection percentages retain full calculated precision.
AREA_EPSILON_SQUARE_METERS = 0.25


def load_rows(path: Path) -> dict[str, dict]:
    return {row["id"]: row for row in GR.load_rows(path)}


def support_by_case(directory: Path) -> dict[str, dict]:
    result = {}
    for path in sorted(directory.glob("*.json")):
        record = json.loads(path.read_text())
        for case_id in record.get("case_ids", []):
            result[case_id] = record
    return result


def clip_around_support(support_geometry: Any, meters: float = 50.0) -> Any:
    center = support_geometry.representative_point()
    forward, inverse = GR.local_transformers(center.x, center.y)
    local = transform_geometry(forward.transform, support_geometry)
    minx, miny, maxx, maxy = local.bounds
    return transform_geometry(inverse.transform, box(minx - meters, miny - meters, maxx + meters, maxy + meters))


def prepare_features(task: str, spatial_record: dict, support_geometry: Any) -> list[dict]:
    features = []
    clip = clip_around_support(support_geometry)
    for capture in spatial_record.get("captures", []):
        raw = capture.get("raw_response", {})
        if GR.sha256(raw) != capture.get("response_sha256"):
            raise GR.GeospatialReviewError("support-centered spatial response hash mismatch")
        for feature in raw.get("features", []):
            attributes = feature.get("attributes", {})
            raw_geometry = feature.get("geometry")
            if task in {"fema_sfha", "historic_district"}:
                geometry, _ = GR.esri_polygon(raw_geometry, clip)
                if geometry.is_empty:
                    continue
            else:
                if not isinstance(raw_geometry, dict) or not isinstance(raw_geometry.get("x"), (int, float)) or not isinstance(raw_geometry.get("y"), (int, float)):
                    raise GR.GeospatialReviewError("EPA candidate has no numeric point geometry")
                geometry = Point(float(raw_geometry["x"]), float(raw_geometry["y"]))
            features.append(
                {
                    "source": capture.get("source"),
                    "attributes": attributes,
                    "geometry": geometry,
                    "key": GR.feature_key(task, str(capture.get("source", "")), attributes),
                }
            )
    return features


def local_context(support_geometry: Any) -> tuple[Any, Any, Any]:
    center = support_geometry.representative_point()
    forward, inverse = GR.local_transformers(center.x, center.y)
    return transform_geometry(forward.transform, support_geometry), forward, inverse


def percent(part: Any, whole: Any) -> float:
    return round(100.0 * part.area / whole.area, 6) if whole.area else 0.0


def fema_relation(support_geometry: Any, features: list[dict]) -> dict:
    support_local, forward, _ = local_context(support_geometry)
    entries = []
    all_polygons = []
    sfha_polygons = []
    non_sfha_polygons = []
    for feature in features:
        local = transform_geometry(forward.transform, feature["geometry"])
        intersection = support_local.intersection(local)
        if intersection.is_empty:
            continue
        attrs = feature["attributes"]
        is_sfha = attrs.get("SFHA_TF") == "T"
        entries.append(
            {
                "zone": attrs.get("FLD_ZONE"),
                "in_sfha": is_sfha,
                "support_area_percent": percent(intersection, support_local),
                "feature_key": list(feature["key"]),
            }
        )
        all_polygons.append(local)
        (sfha_polygons if is_sfha else non_sfha_polygons).append(local)
    if not all_polygons:
        return {"classification": "blocked_source_coverage", "reason": "no FEMA polygon covers the official property support", "zones": []}
    covered = unary_union(all_polygons)
    uncovered = support_local.difference(covered).area
    if uncovered > AREA_EPSILON_SQUARE_METERS:
        return {
            "classification": "blocked_source_coverage",
            "reason": "captured FEMA polygons leave part of the official property support uncovered",
            "uncovered_square_meters": round(uncovered, 6),
            "zones": entries,
        }
    sfha = unary_union(sfha_polygons) if sfha_polygons else None
    non_sfha = unary_union(non_sfha_polygons) if non_sfha_polygons else None
    sfha_area = support_local.intersection(sfha).area if sfha is not None else 0.0
    non_sfha_area = support_local.intersection(non_sfha).area if non_sfha is not None else 0.0
    if sfha_area > AREA_EPSILON_SQUARE_METERS and non_sfha_area > AREA_EPSILON_SQUARE_METERS:
        # Overlap between contradictory FEMA attributes is not allowed to turn
        # into "yes" merely because the SFHA union happens to cover everything.
        classification = "mixed"
    elif sfha is not None and sfha.covers(support_local):
        classification = "certain_yes"
    elif non_sfha is not None and non_sfha.covers(support_local):
        classification = "certain_no"
    else:
        classification = "mixed"
    return {
        "classification": classification,
        "zones": entries,
        "sfha_support_area_percent": round(100.0 * sfha_area / support_local.area, 6),
        "non_sfha_support_area_percent": round(100.0 * non_sfha_area / support_local.area, 6),
        "uncovered_square_meters": round(uncovered, 6),
    }


def historic_relation(support_geometry: Any, features: list[dict]) -> dict:
    support_local, forward, _ = local_context(support_geometry)
    districts = []
    district_polygons = []
    for feature in features:
        attrs = feature["attributes"]
        if str(attrs.get("ResType", "")).lower() != "district" or str(attrs.get("STATUS", "")).lower() != "listed":
            continue
        local = transform_geometry(forward.transform, feature["geometry"])
        intersection = support_local.intersection(local)
        if intersection.is_empty or intersection.area <= AREA_EPSILON_SQUARE_METERS:
            continue
        district_polygons.append(local)
        districts.append(
            {
                "name": attrs.get("RESNAME"),
                "support_area_percent": percent(intersection, support_local),
                "feature_key": list(feature["key"]),
            }
        )
    if not district_polygons:
        classification = "certain_no"
    elif unary_union(district_polygons).covers(support_local):
        classification = "certain_yes"
    else:
        classification = "mixed"
    return {"classification": classification, "districts": sorted(districts, key=lambda item: str(item["name"]))}


def contamination_relation(support_geometry: Any, features: list[dict]) -> dict:
    support_local, forward, _ = local_context(support_geometry)
    buffers = []
    sites = []
    for feature in features:
        local = transform_geometry(forward.transform, feature["geometry"])
        threshold = local.buffer(EPA_THRESHOLD_METERS)
        min_distance = support_local.distance(local)
        max_distance = max(local.distance(Point(coordinate)) for coordinate in support_local.convex_hull.exterior.coords)
        if threshold.intersects(support_local):
            buffers.append(threshold)
            sites.append(
                {
                    "feature_key": list(feature["key"]),
                    "minimum_distance_meters": round(min_distance, 6),
                    "maximum_distance_meters": round(max_distance, 6),
                }
            )
    if not buffers:
        classification = "certain_no"
    elif unary_union(buffers).covers(support_local):
        classification = "certain_yes"
    else:
        classification = "mixed"
    return {"classification": classification, "radius_miles": 0.25, "intersecting_site_count": len(sites), "sites": sites}


def compare_to_point_gold(row: dict, classification: str) -> str:
    key = {"fema_sfha": "in_sfha", "historic_district": "in_historic_district", "contamination_nearby": "has_nearby_site"}[row["task"]]
    gold = bool(row["answer"][key])
    if classification == "certain_yes":
        return "agrees" if gold else "changes"
    if classification == "certain_no":
        return "agrees" if not gold else "changes"
    if classification == "mixed":
        return "point_answer_hides_property_boundary_crossing"
    return "not_comparable"


def review_case(row: dict, support_record: dict, spatial_record: dict) -> dict:
    if spatial_record.get("status") != "captured" or not support_record.get("support"):
        return {
            "case_id": row["id"],
            "task": row["task"],
            "status": "blocked",
            "classification": "blocked_property_identity_or_geometry",
            "comparison_to_census_point_gold": "not_comparable",
            "issues": support_record.get("issues", []) or ["no official property support"],
        }
    if GR.sha256(support_record) != spatial_record.get("property_support_sha256"):
        raise GR.GeospatialReviewError(f"{row['id']}: property support changed after federal capture")
    support_geometry = shape(support_record["support"]["geometry"])
    features = prepare_features(row["task"], spatial_record, support_geometry)
    if row["task"] == "fema_sfha":
        relation = fema_relation(support_geometry, features)
    elif row["task"] == "historic_district":
        relation = historic_relation(support_geometry, features)
    else:
        relation = contamination_relation(support_geometry, features)
    classification = relation["classification"]
    status = "blocked" if classification.startswith("blocked_") else (
        "provisional" if support_record["status"].startswith("provisional_") else "reviewed"
    )
    anchor = support_record["support"].get("address_point")
    anchor_answer, anchor_error = (None, None)
    if anchor:
        anchor_answer, anchor_error = GR.derive(row["task"], anchor["longitude"], anchor["latitude"], features)
    return {
        "case_id": row["id"],
        "task": row["task"],
        "status": status,
        "classification": classification,
        "comparison_to_census_point_gold": compare_to_point_gold(row, classification),
        "census_point_gold": row["answer"],
        "official_address_point_answer": anchor_answer,
        "official_address_point_error": anchor_error,
        "property_support_status": support_record["status"],
        "property_support_kind": support_record["support"]["kind"],
        "property_support_confidence_tier": support_record["support"]["confidence_tier"],
        "census_to_official_anchor_meters": support_record["support"]["census_to_official_anchor_meters"],
        "relation": relation,
        "property_support_sha256": GR.sha256(support_record),
        "support_spatial_evidence_sha256": GR.sha256(spatial_record),
        "issues": [],
    }


def run(dataset: Path, support_dir: Path, spatial_dir: Path) -> dict:
    rows = load_rows(dataset)
    supports = support_by_case(support_dir)
    cases = []
    for path in sorted(spatial_dir.glob("*.json")):
        spatial = json.loads(path.read_text())
        case_id = spatial["case_id"]
        cases.append(review_case(rows[case_id], supports[case_id], spatial))
    statuses = Counter(case["status"] for case in cases)
    classes = Counter(case["classification"] for case in cases)
    comparisons = Counter(case["comparison_to_census_point_gold"] for case in cases)
    return {
        "schema_version": "groundtruth_geo_property_support_review.v1",
        "reviewed_at": GR.utc_now(),
        "review_status": "automated_property_geometry_review_not_independent_professional",
        "independent_professional_review": False,
        "status": "blocked" if statuses.get("blocked") else ("provisional" if statuses.get("provisional") else "reviewed"),
        "semantics": {
            "certain_yes": "Every location in the selected official property support produces yes.",
            "certain_no": "Every location in the selected official property support produces no.",
            "mixed": "The decision boundary crosses the selected official property support; a single-point answer is location-dependent.",
        },
        "summary": {
            "cases": len(cases),
            "statuses": dict(sorted(statuses.items())),
            "classifications": dict(sorted(classes.items())),
            "comparisons_to_census_point_gold": dict(sorted(comparisons.items())),
        },
        "cases": cases,
        "claim_boundaries": [
            "This is an automated screen over public official GIS geometry, not a survey or regulatory determination.",
            "A current official address-to-building or address-to-parcel link is required; ambiguity blocks the result.",
            "Older building-footprint vintages remain provisional even when geometry calculations succeed.",
            "No automated result is labeled independent professional judgment.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "groundtruth_geo.jsonl")
    parser.add_argument("--support-dir", type=Path, default=SUPPORT_DIR)
    parser.add_argument("--spatial-dir", type=Path, default=SPATIAL_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.dataset, args.support_dir, args.spatial_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(GR.canonical_json(report) + b"\n")
    print(json.dumps({key: report[key] for key in ("status", "review_status", "summary")}, indent=2, sort_keys=True))
    # An evidence-blocked case is a successful fail-closed review outcome.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
