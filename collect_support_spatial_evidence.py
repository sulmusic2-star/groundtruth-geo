#!/usr/bin/env python3
"""Capture federal decision geometry around official local property supports."""

from __future__ import annotations

import argparse
import json
import math
import urllib.parse
from pathlib import Path

from shapely.geometry import shape

import collect_spatial_evidence as CSE


ROOT = Path(__file__).resolve().parent
SUPPORT_DIR = ROOT / "property_support" / "records"
OUTPUT_DIR = ROOT / "property_support" / "spatial_records"
PUBLIC_REVIEW = ROOT / "proof" / "geospatial-review-public-20260821.json"
SUPPORT_FILE_BY_ADDRESS = {
    "1300 OCEAN DR, MIAMI BEACH, FL": "miami_beach.json",
    "10 E LIBERTY ST, SAVANNAH, GA": "savannah.json",
    "600 CONGRESS AVE, AUSTIN, TX": "austin.json",
    "1600 PENNSYLVANIA AVE NW, WASHINGTON, DC": "washington_dc.json",
    "233 S WACKER DR, CHICAGO, IL": "chicago.json",
    "100 N TAMPA ST, TAMPA, FL": "tampa.json",
}
BUFFER_METERS = 25.0
EPA_THRESHOLD_METERS = 0.25 * 1609.344


def load_rows(path: Path) -> dict[str, dict]:
    return {row["id"]: row for row in CSE.load_rows(path)}


def expanded_envelope(bounds: tuple[float, float, float, float], meters: float) -> str:
    minx, miny, maxx, maxy = bounds
    mid_lat = (miny + maxy) / 2
    lat_delta = meters / 110_574.0
    lon_delta = meters / max(111_320.0 * math.cos(math.radians(mid_lat)), 1.0)
    return f"{minx-lon_delta:.12f},{miny-lat_delta:.12f},{maxx+lon_delta:.12f},{maxy+lat_delta:.12f}"


def support_specs(task: str, bounds: tuple[float, float, float, float]) -> tuple[list[tuple[str, str]], float]:
    common = {
        "f": "json",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "true",
        "outSR": "4326",
        "returnZ": "false",
        "returnM": "false",
    }
    if task == "fema_sfha":
        params = dict(common)
        params.update(
            {
                "geometry": expanded_envelope(bounds, BUFFER_METERS),
                "geometryType": "esriGeometryEnvelope",
                "outFields": "OBJECTID,DFIRM_ID,FLD_AR_ID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,SOURCE_CIT,GFID,GlobalID",
                "maxAllowableOffset": str(CSE.MAX_POLYGON_OFFSET_DEGREES),
                "geometryPrecision": "8",
            }
        )
        return [("FEMA National Flood Hazard Layer", CSE.build_url(CSE.layer_url(task) + "/query", params))], BUFFER_METERS
    if task == "historic_district":
        params = dict(common)
        params.update(
            {
                "geometry": expanded_envelope(bounds, BUFFER_METERS),
                "geometryType": "esriGeometryEnvelope",
                "outFields": "OBJECTID,NRIS_Refnum,RESNAME,ResType,STATUS,CR_ID,PROPERTY_ID,EDIT_DATE,SOURCE,SRC_DATE,SRC_ACCU,MAP_METHOD",
                "maxAllowableOffset": str(CSE.MAX_POLYGON_OFFSET_DEGREES),
                "geometryPrecision": "8",
            }
        )
        return [("National Park Service National Register polygons", CSE.build_url(CSE.layer_url(task) + "/query", params))], BUFFER_METERS
    if task == "contamination_nearby":
        candidate_buffer = EPA_THRESHOLD_METERS + BUFFER_METERS
        specs = []
        for layer, label in ((0, "Superfund"), (5, "Brownfields")):
            params = dict(common)
            params.update(
                {
                    "geometry": expanded_envelope(bounds, candidate_buffer),
                    "geometryType": "esriGeometryEnvelope",
                    "outFields": "*",
                }
            )
            specs.append((f"EPA Envirofacts {label}", CSE.build_url(CSE.layer_url(task, layer) + "/query", params)))
        return specs, candidate_buffer
    raise CSE.SpatialEvidenceError(f"unsupported task {task}")


def collect_case(row: dict, support_record: dict, captured_at: str) -> dict:
    support = support_record.get("support")
    if not support:
        return {
            "schema_version": "groundtruth_geo_support_spatial_evidence.v1",
            "case_id": row["id"],
            "task": row["task"],
            "captured_at": captured_at,
            "status": "blocked_no_property_support",
            "property_support_sha256": CSE.sha256(support_record),
            "captures": [],
        }
    geometry = shape(support["geometry"])
    specs, buffer_meters = support_specs(row["task"], geometry.bounds)
    captures = []
    for source, url in specs:
        payload = CSE.request_json(url)
        features = payload.get("features")
        if not isinstance(features, list):
            raise CSE.SpatialEvidenceError(f"{row['id']}: {source} returned no feature list")
        captures.append(
            {
                "source": source,
                "record_url": url,
                "response_sha256": CSE.sha256(payload),
                "returned_record_count": len(features),
                "raw_response": payload,
            }
        )
    return {
        "schema_version": "groundtruth_geo_support_spatial_evidence.v1",
        "case_id": row["id"],
        "task": row["task"],
        "captured_at": captured_at,
        "status": "captured",
        "property_support_sha256": CSE.sha256(support_record),
        "property_support_status": support_record["status"],
        "support_kind": support["kind"],
        "support_confidence_tier": support["confidence_tier"],
        "candidate_envelope_buffer_meters": buffer_meters,
        "max_polygon_offset_degrees": CSE.MAX_POLYGON_OFFSET_DEGREES if row["task"] != "contamination_nearby" else None,
        "captures": captures,
        "claim_boundary": "Federal candidate geometry around an official local property support; automated screening evidence, not a professional determination.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "groundtruth_geo.jsonl")
    parser.add_argument("--review", type=Path, default=PUBLIC_REVIEW)
    parser.add_argument("--support-dir", type=Path, default=SUPPORT_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    rows = load_rows(args.dataset)
    review = json.loads(args.review.read_text())
    sensitive_ids = {
        case["case_id"]
        for case in review["cases"]
        if "sensitive" in case.get("perturbation_flags", [])
    }
    captured_at = CSE.utc_now()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for case_id in sorted(sensitive_ids):
        row = rows[case_id]
        support_path = args.support_dir / SUPPORT_FILE_BY_ADDRESS[row["address"]]
        support_record = json.loads(support_path.read_text())
        record = collect_case(row, support_record, captured_at)
        output = args.output_dir / f"{case_id}.json"
        output.write_bytes(CSE.canonical_json(record) + b"\n")
        results[case_id] = {
            "status": record["status"],
            "captures": len(record["captures"]),
            "returned_features": sum(item["returned_record_count"] for item in record["captures"]),
        }
    print(json.dumps({"captured_at": captured_at, "cases": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
