#!/usr/bin/env python3
"""Create and compare append-only GroundTruth-Geo source snapshots.

The first snapshot is a real baseline, not proof of historical stability. Future
captures compare semantic records, geometry, classifications, raw responses,
and layer schemas separately so harmless metadata churn is not confused with a
changed property answer.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
HISTORY_ROOT = ROOT / "history" / "snapshots"


class HistoryError(RuntimeError):
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


def stable_features(captures: list[dict], include_geometry: bool) -> list[dict]:
    result = []
    for capture in captures:
        source = capture.get("source")
        for feature in capture.get("raw_response", {}).get("features", []):
            item = {"source": source, "attributes": feature.get("attributes", {})}
            if include_geometry:
                item["geometry"] = feature.get("geometry")
            result.append(item)
    return sorted(result, key=lambda value: canonical_json(value))


def schema_projection(metadata: dict) -> dict:
    return {
        "name": metadata.get("name"),
        "type": metadata.get("type"),
        "geometryType": metadata.get("geometryType"),
        "spatialReference": metadata.get("spatialReference") or metadata.get("sourceSpatialReference"),
        "fields": [
            {
                "name": field.get("name"),
                "type": field.get("type"),
                "length": field.get("length"),
                "domain": field.get("domain"),
            }
            for field in metadata.get("fields", [])
        ],
        "capabilities": metadata.get("capabilities"),
        "advancedQueryCapabilities": metadata.get("advancedQueryCapabilities"),
    }


def case_snapshot(root: Path, row: dict, spatial_dir: Path) -> dict:
    evidence_path = root / row["evidence_path"]
    spatial_path = spatial_dir / f"{row['id']}.json"
    if not evidence_path.exists() or not spatial_path.exists():
        return {
            "case_id": row["id"],
            "task": row["task"],
            "available": False,
            "missing": [
                label
                for label, path in (("evidence", evidence_path), ("spatial_evidence", spatial_path))
                if not path.exists()
            ],
        }
    evidence = json.loads(evidence_path.read_text())
    spatial = json.loads(spatial_path.read_text())
    identity = evidence.get("property_identity", {})
    evidence_features = stable_features(evidence.get("official_queries", []), include_geometry=False)
    spatial_attributes = stable_features(spatial.get("captures", []), include_geometry=False)
    spatial_with_geometry = stable_features(spatial.get("captures", []), include_geometry=True)
    return {
        "case_id": row["id"],
        "task": row["task"],
        "available": True,
        "retrieved_at": row.get("retrieved_at"),
        "captured_at": spatial.get("captured_at"),
        "answer_sha256": sha256(row.get("answer")),
        "identity_semantic_sha256": sha256(
            {
                "status": identity.get("status"),
                "matched_address": identity.get("matched_address"),
                "longitude": identity.get("longitude"),
                "latitude": identity.get("latitude"),
            }
        ),
        "official_records_sha256": sha256(evidence_features),
        "spatial_attributes_sha256": sha256(spatial_attributes),
        "geometry_sha256": sha256(spatial_with_geometry),
        "raw_evidence_sha256": sha256(
            {
                "identity": evidence.get("property_identity", {}).get("raw_response"),
                "official": [query.get("raw_response") for query in evidence.get("official_queries", [])],
            }
        ),
        "raw_spatial_evidence_sha256": sha256(
            [capture.get("raw_response") for capture in spatial.get("captures", [])]
        ),
    }


def find_previous(history_root: Path, snapshot_date: str) -> Path | None:
    candidates = sorted(
        path / "manifest.json"
        for path in history_root.iterdir()
        if path.is_dir() and path.name < snapshot_date and (path / "manifest.json").exists()
    ) if history_root.exists() else []
    return candidates[-1] if candidates else None


def build_snapshot(root: Path, dataset: Path, spatial_dir: Path, history_root: Path, snapshot_date: str) -> dict:
    rows = load_rows(dataset)
    cases = [case_snapshot(root, row, spatial_dir) for row in rows]
    metadata = []
    metadata_dir = spatial_dir.parent / "metadata"
    for path in sorted(metadata_dir.glob("*.json")):
        payload = json.loads(path.read_text())
        metadata.append(
            {
                "source_id": path.stem,
                "current_version": payload.get("currentVersion"),
                "schema_sha256": sha256(schema_projection(payload)),
                "raw_metadata_sha256": sha256(payload),
            }
        )
    previous_path = find_previous(history_root, snapshot_date)
    previous = None
    if previous_path:
        previous = {
            "manifest": str(previous_path.relative_to(root)),
            "manifest_sha256": hashlib.sha256(previous_path.read_bytes()).hexdigest(),
        }
    content = {"cases": cases, "layer_metadata": metadata}
    return {
        "schema_version": "groundtruth_geo_source_snapshot.v1",
        "snapshot_date": snapshot_date,
        "generated_at": utc_now(),
        "provenance_model": {
            "entity": "dated official-response and derived-semantic snapshot",
            "activity": "source_history.py capture",
            "agent": "GroundTruth-Geo automated collector",
            "was_revision_of": previous,
        },
        "previous_snapshot": previous,
        "content_sha256": sha256(content),
        **content,
        "claim_boundary": "First real snapshot seeds history; stability and change rates require later captures. Hashes prove local byte identity, not government signatures.",
    }


def classify_case_change(before: dict | None, after: dict | None) -> str:
    if before is None:
        return "case_added"
    if after is None:
        return "case_removed"
    if not before.get("available") or not after.get("available"):
        return "source_unavailable"
    if before.get("answer_sha256") != after.get("answer_sha256"):
        return "classification_change"
    if before.get("identity_semantic_sha256") != after.get("identity_semantic_sha256"):
        return "property_identity_change"
    if before.get("geometry_sha256") != after.get("geometry_sha256"):
        return "geometry_change"
    if (
        before.get("official_records_sha256") != after.get("official_records_sha256")
        or before.get("spatial_attributes_sha256") != after.get("spatial_attributes_sha256")
    ):
        return "record_change"
    if (
        before.get("raw_evidence_sha256") != after.get("raw_evidence_sha256")
        or before.get("raw_spatial_evidence_sha256") != after.get("raw_spatial_evidence_sha256")
    ):
        return "metadata_only_change"
    return "unchanged"


def classify_metadata_change(before: dict | None, after: dict | None) -> str:
    if before is None:
        return "source_added"
    if after is None:
        return "source_removed"
    if before.get("schema_sha256") != after.get("schema_sha256"):
        return "schema_change"
    if before.get("raw_metadata_sha256") != after.get("raw_metadata_sha256"):
        return "metadata_only_change"
    return "unchanged"


def diff_snapshots(before: dict, after: dict) -> dict:
    before_cases = {item["case_id"]: item for item in before.get("cases", [])}
    after_cases = {item["case_id"]: item for item in after.get("cases", [])}
    case_changes = [
        {
            "case_id": case_id,
            "task": (after_cases.get(case_id) or before_cases.get(case_id) or {}).get("task"),
            "change": classify_case_change(before_cases.get(case_id), after_cases.get(case_id)),
        }
        for case_id in sorted(set(before_cases) | set(after_cases))
    ]
    before_meta = {item["source_id"]: item for item in before.get("layer_metadata", [])}
    after_meta = {item["source_id"]: item for item in after.get("layer_metadata", [])}
    metadata_changes = [
        {
            "source_id": source_id,
            "change": classify_metadata_change(before_meta.get(source_id), after_meta.get(source_id)),
        }
        for source_id in sorted(set(before_meta) | set(after_meta))
    ]
    counts: dict[str, int] = {}
    for item in case_changes + metadata_changes:
        counts[item["change"]] = counts.get(item["change"], 0) + 1
    actionable = {
        "classification_change",
        "property_identity_change",
        "geometry_change",
        "record_change",
        "source_unavailable",
        "case_added",
        "case_removed",
        "schema_change",
        "source_added",
        "source_removed",
    }
    return {
        "schema_version": "groundtruth_geo_source_diff.v1",
        "before": before.get("snapshot_date"),
        "after": after.get("snapshot_date"),
        "status": "review_required" if any(item["change"] in actionable for item in case_changes + metadata_changes) else "no_semantic_change",
        "counts": dict(sorted(counts.items())),
        "case_changes": case_changes,
        "metadata_changes": metadata_changes,
    }


def validate_manifest(path: Path, root: Path) -> list[str]:
    errors = []
    manifest = json.loads(path.read_text())
    content = {"cases": manifest.get("cases", []), "layer_metadata": manifest.get("layer_metadata", [])}
    if sha256(content) != manifest.get("content_sha256"):
        errors.append(f"{path}: content hash mismatch")
    previous = manifest.get("previous_snapshot")
    if previous:
        previous_path = root / previous.get("manifest", "")
        if not previous_path.exists():
            errors.append(f"{path}: previous manifest is missing")
        elif hashlib.sha256(previous_path.read_bytes()).hexdigest() != previous.get("manifest_sha256"):
            errors.append(f"{path}: previous manifest hash mismatch")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--spatial-dir", type=Path)
    parser.add_argument("--history-root", type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--capture", action="store_true")
    group.add_argument("--validate", action="store_true")
    group.add_argument("--diff", nargs=2, metavar=("BEFORE", "AFTER"), type=Path)
    parser.add_argument("--snapshot-date")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    dataset = (args.dataset or (root / "groundtruth_geo.jsonl")).resolve()
    spatial_dir = (args.spatial_dir or (root / "spatial_evidence" / "records")).resolve()
    history_root = (args.history_root or (root / "history" / "snapshots")).resolve()
    if args.capture:
        snapshot_date = args.snapshot_date or dt.date.today().isoformat()
        destination = history_root / snapshot_date / "manifest.json"
        if destination.exists():
            raise HistoryError(f"append-only snapshot already exists: {destination}")
        manifest = build_snapshot(root, dataset, spatial_dir, history_root, snapshot_date)
        destination.parent.mkdir(parents=True, exist_ok=False)
        destination.write_bytes(canonical_json(manifest) + b"\n")
        result = {"status": "captured", "manifest": str(destination), "cases": len(manifest["cases"])}
    elif args.validate:
        manifests = sorted(history_root.glob("*/manifest.json"))
        errors = [error for path in manifests for error in validate_manifest(path, root)]
        result = {"status": "passed" if not errors and manifests else "failed", "manifests": len(manifests), "errors": errors}
    else:
        before = json.loads(args.diff[0].read_text())
        after = json.loads(args.diff[1].read_text())
        result = diff_snapshots(before, after)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(canonical_json(result) + b"\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"captured", "passed", "no_semantic_change", "review_required"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
