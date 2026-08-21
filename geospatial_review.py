#!/usr/bin/env python3
"""Third-engine spatial and boundary-perturbation review for GroundTruth-Geo.

This program uses GEOS through Shapely and PROJ through PyProj. It imports
neither evidence-generation implementation nor the replicated reviewer. It
rebuilds geometry from stored government responses, derives the center answer,
then moves the test point through a deterministic 57-point matrix.

Passing is multi-engine automated replication, not independent human or
professional review.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any

import pyproj
import shapely
from pyproj import CRS, Geod, Transformer
from shapely.errors import GEOSException
from shapely.geometry import GeometryCollection, Point, Polygon, box
from shapely.ops import transform as transform_geometry
from shapely.validation import explain_validity, make_valid


ROOT = Path(__file__).resolve().parent
RADII_METERS = (0.0, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0)
BEARINGS_DEGREES = tuple(range(0, 360, 45))
EPA_THRESHOLD_METERS = 0.25 * 1609.344
BOUNDARY_EPSILON_METERS = 0.10
GEOD = Geod(ellps="WGS84")


class GeospatialReviewError(RuntimeError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(value: Any) -> str:
    data = value if isinstance(value, bytes) else canonical_json(value)
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def normalized_ring(raw_ring: Any) -> list[tuple[float, float]]:
    if not isinstance(raw_ring, list) or len(raw_ring) < 3:
        raise GeospatialReviewError("polygon ring has fewer than three positions")
    result = []
    for position in raw_ring:
        if not isinstance(position, list) or len(position) < 2:
            raise GeospatialReviewError("polygon position is not an x/y array")
        x, y = position[0], position[1]
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            raise GeospatialReviewError("polygon position is not numeric")
        if not math.isfinite(x) or not math.isfinite(y):
            raise GeospatialReviewError("polygon position is not finite")
        result.append((float(x), float(y)))
    if result[0] != result[-1]:
        result.append(result[0])
    if len(set(result[:-1])) < 3:
        raise GeospatialReviewError("polygon ring has fewer than three distinct positions")
    return result


def esri_polygon(raw_geometry: dict, clip_geometry: Any) -> tuple[Any, dict]:
    """Apply Esri's documented even-odd ring fill rule with GEOS."""
    rings = raw_geometry.get("rings") if isinstance(raw_geometry, dict) else None
    if not isinstance(rings, list) or not rings:
        raise GeospatialReviewError("feature has no Esri polygon rings")
    geometry: Any = GeometryCollection()
    ring_count = 0
    intersecting_ring_count = 0
    for raw_ring in rings:
        ring_polygon = Polygon(normalized_ring(raw_ring))
        if ring_polygon.is_empty:
            raise GeospatialReviewError("feature has an empty polygon ring")
        try:
            clipped = ring_polygon.intersection(clip_geometry)
        except GEOSException:
            clipped = make_valid(ring_polygon).intersection(clip_geometry)
        if not clipped.is_empty:
            geometry = geometry.symmetric_difference(clipped)
            intersecting_ring_count += 1
        ring_count += 1
    if geometry.is_empty:
        return geometry, {
            "ring_count": ring_count,
            "intersecting_ring_count": intersecting_ring_count,
            "valid_before_final_repair": True,
            "validity_reason": "Valid Geometry (empty after bounded clipping)",
            "final_repair_applied": False,
        }
    was_valid = geometry.is_valid
    validity_reason = explain_validity(geometry)
    repaired = False
    if not was_valid:
        geometry = make_valid(geometry)
        repaired = True
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise GeospatialReviewError(f"even-odd reconstruction produced {geometry.geom_type}")
    return geometry, {
        "ring_count": ring_count,
        "intersecting_ring_count": intersecting_ring_count,
        "valid_before_final_repair": was_valid,
        "validity_reason": validity_reason,
        "final_repair_applied": repaired,
    }


def local_transformers(lon: float, lat: float) -> tuple[Transformer, Transformer]:
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat:.12f} +lon_0={lon:.12f} +datum=WGS84 +units=m +no_defs"
    )
    return (
        Transformer.from_crs("EPSG:4326", local, always_xy=True),
        Transformer.from_crs(local, "EPSG:4326", always_xy=True),
    )


def feature_key(task: str, source: str, attributes: dict) -> tuple[str, ...]:
    if task == "fema_sfha":
        return (str(attributes.get("GFID") or attributes.get("GlobalID") or attributes.get("FLD_AR_ID")),)
    if task == "historic_district":
        return (str(attributes.get("CR_ID") or attributes.get("PROPERTY_ID") or attributes.get("NRIS_Refnum")),)
    label = "Superfund" if "Superfund" in source else "Brownfields"
    return (
        label,
        str(attributes.get("registry_id") or ""),
        str(attributes.get("pgm_sys_id") or attributes.get("site_id") or ""),
    )


def prepare_features(task: str, spatial_record: dict) -> tuple[list[dict], list[dict]]:
    features = []
    diagnostics = []
    center = spatial_record.get("center", {})
    lon, lat = center.get("longitude"), center.get("latitude")
    clip_geometry = None
    if task in {"fema_sfha", "historic_district"}:
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            raise GeospatialReviewError("spatial evidence has no numeric center")
        forward, inverse = local_transformers(lon, lat)
        capture_radius = float(spatial_record.get("capture_radius_meters") or 150.0)
        clip_radius = min(125.0, max(capture_radius - 5.0, 105.0))
        clip_geometry = transform_geometry(inverse.transform, box(-clip_radius, -clip_radius, clip_radius, clip_radius))
    for capture in spatial_record.get("captures", []):
        source = str(capture.get("source", ""))
        raw = capture.get("raw_response", {})
        if sha256(raw) != capture.get("response_sha256"):
            raise GeospatialReviewError(f"{spatial_record['case_id']}: spatial response hash mismatch")
        for feature in raw.get("features", []):
            attributes = feature.get("attributes", {})
            geometry = feature.get("geometry")
            if task in {"fema_sfha", "historic_district"}:
                parsed, diagnostic = esri_polygon(geometry, clip_geometry)
                if parsed.is_empty:
                    continue
                diagnostics.append({"feature_key": feature_key(task, source, attributes), **diagnostic})
            else:
                if not isinstance(geometry, dict) or not isinstance(geometry.get("x"), (int, float)) or not isinstance(geometry.get("y"), (int, float)):
                    raise GeospatialReviewError("EPA candidate has no numeric point geometry")
                parsed = Point(float(geometry["x"]), float(geometry["y"]))
            features.append(
                {
                    "source": source,
                    "attributes": attributes,
                    "geometry": parsed,
                    "key": feature_key(task, source, attributes),
                }
            )
    return features, diagnostics


def derive(task: str, lon: float, lat: float, features: list[dict]) -> tuple[dict | None, str | None]:
    point = Point(lon, lat)
    if task == "fema_sfha":
        covering = [feature for feature in features if feature["geometry"].covers(point)]
        if len(covering) != 1:
            return None, f"expected exactly one covering FEMA polygon; got {len(covering)}"
        attrs = covering[0]["attributes"]
        if attrs.get("SFHA_TF") not in {"T", "F"} or not attrs.get("FLD_ZONE"):
            return None, "covering FEMA polygon lacks SFHA_TF or FLD_ZONE"
        return {"in_sfha": attrs["SFHA_TF"] == "T", "zone": attrs["FLD_ZONE"]}, None
    if task == "historic_district":
        names = sorted(
            {
                str(feature["attributes"].get("RESNAME"))
                for feature in features
                if str(feature["attributes"].get("ResType", "")).lower() == "district"
                and str(feature["attributes"].get("STATUS", "")).lower() == "listed"
                and feature["geometry"].covers(point)
                and feature["attributes"].get("RESNAME")
            }
        )
        return {
            "in_historic_district": bool(names),
            "district": names[0] if len(names) == 1 else ("; ".join(names) if names else None),
            "districts": names,
        }, None
    if task == "contamination_nearby":
        included = {}
        for feature in features:
            site = feature["geometry"]
            _, _, distance_meters = GEOD.inv(lon, lat, site.x, site.y)
            if distance_meters <= EPA_THRESHOLD_METERS + 1e-7:
                included[feature["key"]] = feature
        return {
            "has_nearby_site": bool(included),
            "count": len(included),
            "radius_miles": 0.25,
            "programs": ["Brownfields", "Superfund"],
        }, None
    raise GeospatialReviewError(f"unsupported task {task}")


def perturbation_points(lon: float, lat: float) -> list[dict]:
    points = [{"radius_meters": 0.0, "bearing_degrees": None, "longitude": lon, "latitude": lat}]
    for radius in RADII_METERS[1:]:
        for bearing in BEARINGS_DEGREES:
            moved_lon, moved_lat, _ = GEOD.fwd(lon, lat, bearing, radius)
            points.append(
                {
                    "radius_meters": radius,
                    "bearing_degrees": bearing,
                    "longitude": moved_lon,
                    "latitude": moved_lat,
                }
            )
    return points


def nearest_boundary(task: str, lon: float, lat: float, features: list[dict], capture_radius: float | None) -> dict:
    if task == "contamination_nearby":
        if not features:
            lower_bound = max((capture_radius or 0.35 * 1609.344) - EPA_THRESHOLD_METERS, 0.0)
            return {"kind": "threshold_margin_lower_bound", "meters": round(lower_bound, 6)}
        margins = []
        for feature in features:
            site = feature["geometry"]
            _, _, distance = GEOD.inv(lon, lat, site.x, site.y)
            margins.append(abs(distance - EPA_THRESHOLD_METERS))
        return {"kind": "nearest_distance_threshold", "meters": round(min(margins), 6)}
    forward, _ = local_transformers(lon, lat)
    point_local = Point(0.0, 0.0)
    if not features:
        return {"kind": "no_feature_within_capture_lower_bound", "meters": float(capture_radius or 0.0)}
    distances = []
    for feature in features:
        local = transform_geometry(forward.transform, feature["geometry"])
        distances.append(point_local.distance(local.boundary))
    return {"kind": "nearest_polygon_boundary", "meters": round(min(distances), 6)}


def perturbation_labels(
    boundary_meters: float,
    changed_count: int,
    unresolved_count: int,
    center_error: str | None,
) -> tuple[str, list[str]]:
    if center_error:
        return "geometry_unavailable", ["geometry_unavailable"]
    flags = []
    if boundary_meters <= BOUNDARY_EPSILON_METERS:
        flags.append("boundary_contact")
    if changed_count or unresolved_count:
        flags.append("sensitive")
    if not flags:
        flags.append("stable_through_100m_tested")
    precedence = (
        "geometry_unavailable",
        "boundary_contact",
        "sensitive",
        "stable_through_100m_tested",
    )
    primary = next(label for label in precedence if label in flags)
    return primary, flags


def review_case(case: dict, spatial_record: dict) -> dict:
    issues = []
    if spatial_record.get("case_id") != case.get("id") or spatial_record.get("task") != case.get("task"):
        issues.append("spatial evidence identity/task mismatch")
    center = spatial_record.get("center", {})
    lon, lat = center.get("longitude"), center.get("latitude")
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        raise GeospatialReviewError(f"{case.get('id')}: spatial record has no center")
    case_lon, case_lat = case.get("longitude"), case.get("latitude")
    if isinstance(case_lon, (int, float)) and isinstance(case_lat, (int, float)):
        if abs(lon - case_lon) > 1e-9 or abs(lat - case_lat) > 1e-9:
            issues.append("spatial evidence center differs from benchmark coordinate")
    try:
        features, geometry_diagnostics = prepare_features(case["task"], spatial_record)
    except Exception as exc:
        return {
            "case_id": case.get("id"),
            "task": case.get("task"),
            "status": "failed",
            "issues": issues + [str(exc)],
            "center_answer": None,
            "perturbation_class": "geometry_unavailable",
        }
    center_answer, center_error = derive(case["task"], lon, lat, features)
    if center_error:
        issues.append(center_error)
    if center_answer != case.get("answer"):
        issues.append("GEOS/PROJ center derivation disagrees with benchmark answer")

    samples = []
    changed = []
    unresolved = []
    for point in perturbation_points(lon, lat):
        answer, error = derive(case["task"], point["longitude"], point["latitude"], features)
        row = {**point, "answer": answer, "error": error}
        samples.append(row)
        if point["radius_meters"] > 0 and error:
            unresolved.append(row)
        elif point["radius_meters"] > 0 and answer != center_answer:
            changed.append(row)
    boundary = nearest_boundary(
        case["task"],
        lon,
        lat,
        features,
        spatial_record.get("capture_radius_meters")
        or (spatial_record.get("candidate_radius_miles") or 0.0) * 1609.344,
    )
    perturbation_class, perturbation_flags = perturbation_labels(
        boundary["meters"], len(changed), len(unresolved), center_error
    )
    first_change = min(
        (row["radius_meters"] for row in changed + unresolved), default=None
    )
    return {
        "case_id": case["id"],
        "task": case["task"],
        "spatial_evidence_sha256": sha256(spatial_record),
        "status": "passed" if not issues else "failed",
        "issues": issues,
        "gold_hidden_during_geometry_preparation": True,
        "center_answer": center_answer,
        "feature_count": len(features),
        "geometry_diagnostics": geometry_diagnostics,
        "nearest_decision_boundary": boundary,
        "perturbation_class": perturbation_class,
        "perturbation_flags": perturbation_flags,
        "first_changed_or_unresolved_radius_meters": first_change,
        "sample_count": len(samples),
        "changed_sample_count": len(changed),
        "unresolved_sample_count": len(unresolved),
        "samples": samples,
    }


def run(root: Path, dataset: Path, spatial_dir: Path) -> dict:
    rows = load_rows(dataset)
    cases = []
    for row in rows:
        spatial_path = spatial_dir / f"{row['id']}.json"
        if not spatial_path.exists():
            cases.append(
                {
                    "case_id": row["id"],
                    "task": row["task"],
                    "status": "failed",
                    "issues": ["spatial evidence is missing"],
                    "center_answer": None,
                    "perturbation_class": "geometry_unavailable",
                }
            )
            continue
        cases.append(review_case(row, json.loads(spatial_path.read_text())))
    status_counts = Counter(case["status"] for case in cases)
    perturbation_counts = Counter(case["perturbation_class"] for case in cases)
    total_samples = sum(case.get("sample_count", 0) for case in cases)
    report = {
        "schema_version": "groundtruth_geo_geospatial_review.v1",
        "reviewed_at": utc_now(),
        "status": "passed" if status_counts.get("failed", 0) == 0 else "failed",
        "review_status": "three_implementation_automated_review_not_independent_human",
        "independent_human_review": False,
        "collection_root": str(root),
        "dataset": str(dataset),
        "reviewer_implementation": "geospatial_review.py; GEOS/Shapely and PROJ/PyProj; no imports from either prior derivation",
        "library_versions": {
            "shapely": shapely.__version__,
            "geos": shapely.geos_version_string,
            "pyproj": pyproj.__version__,
            "proj": pyproj.proj_version_str,
        },
        "matrix": {
            "radii_meters": list(RADII_METERS),
            "bearings_degrees": list(BEARINGS_DEGREES),
            "samples_per_complete_case": 57,
            "boundary_inclusive_predicate": "covers",
        },
        "summary": {
            "cases": len(cases),
            "passed_cases": status_counts.get("passed", 0),
            "failed_cases": status_counts.get("failed", 0),
            "perturbation_classes": dict(sorted(perturbation_counts.items())),
            "perturbation_samples": total_samples,
            "changed_samples": sum(case.get("changed_sample_count", 0) for case in cases),
            "unresolved_samples": sum(case.get("unresolved_sample_count", 0) for case in cases),
        },
        "spatial_evidence_collection_sha256": sha256(
            [
                {"case_id": case.get("case_id"), "spatial_evidence_sha256": case.get("spatial_evidence_sha256")}
                for case in cases
            ]
        ),
        "cases": cases,
        "claim_boundaries": [
            "This is automated replication across three implementations, not independent human or professional review.",
            "Perturbations measure sensitivity to the stored geocoded point; they do not estimate a parcel boundary or survey accuracy.",
            "The matrix is a deterministic stress test, not a representative estimate of U.S. property accuracy.",
            "Sensitive, boundary-contact, missing, or disagreeing cases require abstention or qualified review; results are never averaged together.",
        ],
    }
    return report


def public_receipt(report: dict, include_cases: bool = True) -> dict:
    cases = [
        {
            "case_id": case["case_id"],
            "task": case["task"],
            "status": case["status"],
            "perturbation_class": case["perturbation_class"],
            "perturbation_flags": case.get("perturbation_flags", [case["perturbation_class"]]),
            "first_changed_or_unresolved_radius_meters": case.get("first_changed_or_unresolved_radius_meters"),
            "nearest_decision_boundary": case.get("nearest_decision_boundary"),
        }
        for case in report["cases"]
    ]
    receipt = {
        "schema_version": "groundtruth_geo_geospatial_review_receipt.v1",
        "reviewed_at": report["reviewed_at"],
        "status": report["status"],
        "review_status": report["review_status"],
        "independent_human_review": False,
        "library_versions": report["library_versions"],
        "matrix": report["matrix"],
        "summary": report["summary"],
        "spatial_evidence_collection_sha256": report["spatial_evidence_collection_sha256"],
        "detailed_report_sha256": sha256(report),
        "claim_boundary": "Three automated implementations with boundary perturbation; not independent human review, a survey, or representative field accuracy.",
    }
    if include_cases:
        receipt["cases"] = cases
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--collection", choices=("public", "private"), default="public")
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--spatial-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    dataset = (args.dataset or (root / "groundtruth_geo.jsonl")).resolve()
    spatial_dir = (args.spatial_dir or (root / "spatial_evidence" / "records")).resolve()
    report = run(root, dataset, spatial_dir)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(canonical_json(report) + b"\n")
        if args.collection == "private":
            os.chmod(args.output, 0o600)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_bytes(canonical_json(public_receipt(report, include_cases=args.collection == "public")) + b"\n")
    print(json.dumps({key: report[key] for key in ("status", "review_status", "library_versions", "summary")}, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
