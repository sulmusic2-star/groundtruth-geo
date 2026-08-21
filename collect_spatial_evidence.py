#!/usr/bin/env python3
"""Collect replayable geometry around each GroundTruth-Geo test point.

The existing evidence proves the answer at one coordinate. This collector asks
the same government layers for a bounded neighborhood so a separate geometry
engine can test whether small coordinate changes alter that answer. Collection
and review are intentionally separate programs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "groundtruth_geo.jsonl"
OUTPUT_DIR = ROOT / "spatial_evidence" / "records"
USER_AGENT = "GroundTruth-Geo spatial evidence collector; https://github.com/sulmusic2-star/groundtruth-geo"
CAPTURE_RADIUS_METERS = 150.0
EPA_CANDIDATE_RADIUS_MILES = 0.35
MAX_POLYGON_OFFSET_DEGREES = 0.0000005  # at most about 5.6 cm in WGS84 x/y

TASK_HOSTS = {
    "fema_sfha": "hazards.fema.gov",
    "historic_district": "mapservices.nps.gov",
    "contamination_nearby": "geopub.epa.gov",
}
LAYER_PATHS = {
    "fema_sfha": "/arcgis/rest/services/public/NFHL/MapServer/28",
    "historic_district": "/arcgis/rest/services/cultural_resources/nrhp_locations/MapServer/1",
    "contamination_nearby": (
        "/ArcGIS/rest/services/EMEF/efpoints/MapServer/0",
        "/ArcGIS/rest/services/EMEF/efpoints/MapServer/5",
    ),
}


class SpatialEvidenceError(RuntimeError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(value: Any) -> str:
    data = value if isinstance(value, bytes) else canonical_json(value)
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_rows(dataset: Path) -> list[dict]:
    return [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]


def request_json(url: str, attempts: int = 6) -> dict:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.load(response)
            if payload.get("error"):
                raise SpatialEvidenceError(f"official service error: {payload['error']}")
            return payload
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(min(1 + attempt, 6))
    raise SpatialEvidenceError(f"request failed after {attempts} attempts: {url}: {last_error}")


def build_url(base: str, params: dict[str, str]) -> str:
    return base + "?" + urllib.parse.urlencode(params)


def layer_url(task: str, layer: int | None = None) -> str:
    path = LAYER_PATHS[task]
    if isinstance(path, tuple):
        if layer not in (0, 5):
            raise SpatialEvidenceError(f"invalid EPA layer {layer}")
        path = path[0 if layer == 0 else 1]
    return f"https://{TASK_HOSTS[task]}{path}"


def envelope(lon: float, lat: float, radius_meters: float) -> str:
    # Deliberately conservative WGS84 envelope used only to collect candidates.
    # The independent reviewer performs all decision geometry with PROJ/GEOS.
    lat_delta = radius_meters / 110_574.0
    lon_delta = radius_meters / max(111_320.0 * math.cos(math.radians(lat)), 1.0)
    return f"{lon - lon_delta:.12f},{lat - lat_delta:.12f},{lon + lon_delta:.12f},{lat + lat_delta:.12f}"


def query_specs(task: str, lon: float, lat: float) -> list[tuple[str, str]]:
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
                "geometry": envelope(lon, lat, CAPTURE_RADIUS_METERS),
                "geometryType": "esriGeometryEnvelope",
                "outFields": "OBJECTID,DFIRM_ID,FLD_AR_ID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,SOURCE_CIT,GFID,GlobalID",
                "maxAllowableOffset": str(MAX_POLYGON_OFFSET_DEGREES),
                "geometryPrecision": "8",
            }
        )
        return [("FEMA National Flood Hazard Layer", build_url(layer_url(task) + "/query", params))]
    if task == "historic_district":
        params = dict(common)
        params.update(
            {
                "geometry": envelope(lon, lat, CAPTURE_RADIUS_METERS),
                "geometryType": "esriGeometryEnvelope",
                "outFields": "OBJECTID,NRIS_Refnum,RESNAME,ResType,STATUS,CR_ID,PROPERTY_ID,EDIT_DATE,SOURCE,SRC_DATE,SRC_ACCU,MAP_METHOD",
                "maxAllowableOffset": str(MAX_POLYGON_OFFSET_DEGREES),
                "geometryPrecision": "8",
            }
        )
        return [("National Park Service National Register polygons", build_url(layer_url(task) + "/query", params))]
    if task == "contamination_nearby":
        specs = []
        for layer, label in ((0, "Superfund"), (5, "Brownfields")):
            params = dict(common)
            params.update(
                {
                    "geometry": f"{lon:.12f},{lat:.12f}",
                    "geometryType": "esriGeometryPoint",
                    "distance": str(EPA_CANDIDATE_RADIUS_MILES),
                    "units": "esriSRUnit_StatuteMile",
                    "outFields": "*",
                }
            )
            specs.append((f"EPA Envirofacts {label}", build_url(layer_url(task, layer) + "/query", params)))
        return specs
    raise SpatialEvidenceError(f"unsupported task {task}")


def metadata_urls() -> dict[str, str]:
    return {
        "fema_nfhl_flood_hazard_zones": layer_url("fema_sfha") + "?f=pjson",
        "nps_nrhp_polygons": layer_url("historic_district") + "?f=pjson",
        "epa_superfund_points": layer_url("contamination_nearby", 0) + "?f=pjson",
        "epa_brownfields_points": layer_url("contamination_nearby", 5) + "?f=pjson",
    }


def collect_record(root: Path, row: dict, retrieved_at: str, metadata: dict[str, dict]) -> dict:
    receipt_path = root / row["evidence_path"]
    receipt = json.loads(receipt_path.read_text())
    identity = receipt.get("property_identity", {})
    lon, lat = identity.get("longitude"), identity.get("latitude")
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        raise SpatialEvidenceError(f"{row['id']}: missing numeric evidence coordinate")
    captures = []
    for source, url in query_specs(row["task"], lon, lat):
        payload = request_json(url)
        features = payload.get("features")
        if not isinstance(features, list):
            raise SpatialEvidenceError(f"{row['id']}: {source} returned no feature list")
        captures.append(
            {
                "source": source,
                "record_url": url,
                "response_sha256": sha256(payload),
                "returned_record_count": len(features),
                "raw_response": payload,
            }
        )
    return {
        "schema_version": "groundtruth_geo_spatial_evidence.v1",
        "case_id": row["id"],
        "task": row["task"],
        "captured_at": retrieved_at,
        "center": {"longitude": lon, "latitude": lat},
        "source_evidence_path": row["evidence_path"],
        "source_evidence_sha256": row["evidence_sha256"],
        "capture_radius_meters": CAPTURE_RADIUS_METERS if row["task"] != "contamination_nearby" else None,
        "candidate_radius_miles": EPA_CANDIDATE_RADIUS_MILES if row["task"] == "contamination_nearby" else None,
        "max_polygon_offset_degrees": MAX_POLYGON_OFFSET_DEGREES if row["task"] != "contamination_nearby" else None,
        "layer_metadata_sha256": {key: sha256(value) for key, value in metadata.items()},
        "captures": captures,
        "claim_boundary": "Candidate geometry for automated perturbation review; not a survey, parcel boundary, legal determination, or independent professional review.",
    }


def refresh(root: Path, dataset: Path, output_dir: Path, private: bool = False) -> dict:
    rows = load_rows(dataset)
    captured_at = utc_now()
    metadata = {name: request_json(url) for name, url in metadata_urls().items()}
    records = [collect_record(root, row, captured_at, metadata) for row in rows]
    output_dir.mkdir(parents=True, exist_ok=True)
    if private:
        os.chmod(output_dir.parent, 0o700)
        os.chmod(output_dir, 0o700)
    for record in records:
        path = output_dir / f"{record['case_id']}.json"
        path.write_bytes(canonical_json(record) + b"\n")
        if private:
            os.chmod(path, 0o600)
    metadata_dir = output_dir.parent / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    if private:
        os.chmod(metadata_dir, 0o700)
    for name, payload in metadata.items():
        path = metadata_dir / f"{name}.json"
        path.write_bytes(canonical_json(payload) + b"\n")
        if private:
            os.chmod(path, 0o600)
    return {"status": "captured", "cases": len(records), "captured_at": captured_at}


def validate(root: Path, dataset: Path, output_dir: Path) -> dict:
    errors = []
    rows = load_rows(dataset)
    metadata_dir = output_dir.parent / "metadata"
    metadata = {}
    for name, url in metadata_urls().items():
        path = metadata_dir / f"{name}.json"
        if not path.exists():
            errors.append(f"missing metadata snapshot {path}")
            continue
        payload = json.loads(path.read_text())
        if payload.get("error"):
            errors.append(f"{name}: metadata snapshot contains a service error")
        metadata[name] = payload
    for row in rows:
        path = output_dir / f"{row['id']}.json"
        if not path.exists():
            errors.append(f"{row['id']}: missing spatial evidence")
            continue
        record = json.loads(path.read_text())
        if record.get("case_id") != row["id"] or record.get("task") != row["task"]:
            errors.append(f"{row['id']}: identity/task mismatch")
        source_path = root / record.get("source_evidence_path", "")
        if not source_path.exists() or sha256(json.loads(source_path.read_text())) != record.get("source_evidence_sha256"):
            errors.append(f"{row['id']}: linked source evidence changed")
        expected_count = 2 if row["task"] == "contamination_nearby" else 1
        if len(record.get("captures", [])) != expected_count:
            errors.append(f"{row['id']}: expected {expected_count} captures")
        for capture in record.get("captures", []):
            raw = capture.get("raw_response")
            if not isinstance(raw, dict) or raw.get("error"):
                errors.append(f"{row['id']}: unusable captured response")
                continue
            if sha256(raw) != capture.get("response_sha256"):
                errors.append(f"{row['id']}: captured response hash mismatch")
            if capture.get("returned_record_count") != len(raw.get("features", [])):
                errors.append(f"{row['id']}: captured record count mismatch")
            parsed = urllib.parse.urlsplit(str(capture.get("record_url", "")))
            if parsed.scheme != "https" or (parsed.hostname or "").lower() != TASK_HOSTS[row["task"]]:
                errors.append(f"{row['id']}: capture URL is not the expected government host")
        expected_metadata = record.get("layer_metadata_sha256", {})
        for key, digest in expected_metadata.items():
            if key not in metadata or sha256(metadata[key]) != digest:
                errors.append(f"{row['id']}: layer metadata {key} changed locally")
    return {"status": "passed" if not errors else "failed", "cases": len(rows), "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--private", action="store_true", help="write captured records with owner-only permissions")
    args = parser.parse_args()
    root = args.root.resolve()
    dataset = (args.dataset or (root / "groundtruth_geo.jsonl")).resolve()
    output_dir = (args.output_dir or (root / "spatial_evidence" / "records")).resolve()
    if args.refresh == args.validate:
        parser.error("choose exactly one of --refresh or --validate")
    result = refresh(root, dataset, output_dir, private=args.private) if args.refresh else validate(root, dataset, output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"captured", "passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
