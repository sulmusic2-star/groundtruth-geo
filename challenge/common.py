"""Shared validation and hashing for GroundTruth-Geo blind challenges."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(value: Any) -> str:
    data = value if isinstance(value, bytes) else canonical_json(value)
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_private(path: Path, value: Any, jsonl: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    if jsonl:
        payload = b"".join(canonical_json(item) + b"\n" for item in value)
    else:
        payload = canonical_json(value) + b"\n"
    path.write_bytes(payload)
    path.chmod(0o600)


def validate_submission(document: dict, expected_ids: set[str]) -> list[str]:
    errors = []
    if document.get("schema_version") != "groundtruth_geo_blind_submission.v1":
        errors.append("unsupported submission schema_version")
    participant = document.get("participant")
    if not isinstance(participant, dict):
        errors.append("participant must be an object")
    else:
        for field in ("organization", "system_name", "system_version", "submitted_by"):
            if not str(participant.get(field, "")).strip():
                errors.append(f"participant.{field} is required")
    predictions = document.get("predictions")
    if not isinstance(predictions, list):
        return errors + ["predictions must be an array"]
    seen = set()
    for index, prediction in enumerate(predictions):
        if not isinstance(prediction, dict):
            errors.append(f"predictions[{index}] must be an object")
            continue
        item_id = prediction.get("item_id")
        if item_id in seen:
            errors.append(f"duplicate item_id {item_id}")
        seen.add(item_id)
        if item_id not in expected_ids:
            errors.append(f"unknown item_id {item_id}")
        attempted = prediction.get("attempted")
        if not isinstance(attempted, bool):
            errors.append(f"{item_id}: attempted must be boolean")
        answer = prediction.get("answer")
        if answer is not None and not isinstance(answer, bool):
            errors.append(f"{item_id}: answer must be boolean or null")
        if attempted is False and answer is not None:
            errors.append(f"{item_id}: an abstention must use answer null")
        if attempted is True and answer is None:
            errors.append(f"{item_id}: an attempted answer must be boolean")
        if not isinstance(prediction.get("sources", []), list):
            errors.append(f"{item_id}: sources must be an array")
    missing = expected_ids - seen
    if missing:
        errors.append(f"submission is missing {len(missing)} challenge items")
    return errors
