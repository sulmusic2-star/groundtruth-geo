#!/usr/bin/env python3
"""Audit model predictions for six property-evidence failure modes."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import refresh_evidence


ROOT = Path(__file__).resolve().parent
TASK_KEY = refresh_evidence.TASK_KEYS
OFFICIAL_HOSTS = {
    "fema_sfha": {"hazards.fema.gov", "msc.fema.gov"},
    "historic_district": {"mapservices.nps.gov", "catalog.archives.gov"},
    "contamination_nearby": {"geopub.epa.gov", "enviro.epa.gov"},
}


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def haversine_meters(lon1, lat1, lon2, lat2) -> float:
    radius = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def abstained(prediction: dict | None) -> bool:
    return not prediction or prediction.get("attempted") is False or prediction.get("answer") is None


def evidence_for(row: dict) -> dict:
    return json.loads((ROOT / row["evidence_path"]).read_text())


def score_item(row: dict, prediction: dict | None) -> dict:
    prediction = prediction or {}
    is_abstained = abstained(prediction)
    gold = bool(row["answer"][TASK_KEY[row["task"]]])
    if is_abstained:
        return {
            "item_id": row["id"],
            "task": row["task"],
            "address": row["address"],
            "attempted": False,
            "abstained": True,
            "answer_correct": None,
            "wrong_property": False,
            "wrong_source": False,
            "unsupported_answer": False,
            "unusable_citation": False,
            "failure_to_abstain": False,
            "stale_or_undated_evidence": False,
            "accepted": False,
            "reasons": ["model abstained"],
        }
    reasons = []
    requested_ok = str(prediction.get("requested_address", "")).strip().upper() == row["address"].strip().upper()
    matched_ok = str(prediction.get("matched_address", "")).strip().upper() == row["matched_address"].strip().upper()
    coordinate_ok = False
    try:
        distance = haversine_meters(
            float(prediction["longitude"]),
            float(prediction["latitude"]),
            float(row["longitude"]),
            float(row["latitude"]),
        )
        coordinate_ok = distance <= 100
    except (KeyError, TypeError, ValueError):
        distance = None
    property_ok = requested_ok and (matched_ok or coordinate_ok)
    if not property_ok:
        reasons.append("property identity was missing or did not match the reviewed point")
    sources = [source for source in prediction.get("sources", []) if isinstance(source, dict)]
    official_source = any(
        urlparse(source.get("url", "")).hostname in OFFICIAL_HOSTS[row["task"]]
        for source in sources
    )
    if not official_source:
        reasons.append("no task-appropriate official source")
    evidence = evidence_for(row)
    accepted_record_urls = {query["record_url"] for query in evidence["official_queries"]}
    usable_citations = [
        source
        for source in sources
        if source.get("supports_answer") is True and source.get("url") in accepted_record_urls
    ]
    citation_ok = bool(usable_citations)
    if not citation_ok:
        reasons.append("no supporting record-level citation matching the reviewed query")
    gold_time = parse_time(row["retrieved_at"])
    dated_sources = [parse_time(source.get("retrieved_at")) for source in usable_citations]
    freshness_ok = bool(gold_time and any(source_time and source_time >= gold_time for source_time in dated_sources))
    if not freshness_ok:
        reasons.append("supporting evidence was missing a current retrieval date")
    answer_correct = bool(prediction.get("answer")) == gold
    support_ok = answer_correct and property_ok and official_source and citation_ok
    if not support_ok:
        reasons.append("answer was not fully supported by the reviewed property and record")
    critical_ok = property_ok and official_source and citation_ok and freshness_ok and answer_correct
    return {
        "item_id": row["id"],
        "task": row["task"],
        "address": row["address"],
        "attempted": True,
        "abstained": False,
        "answer_correct": answer_correct,
        "wrong_property": not property_ok,
        "wrong_source": not official_source,
        "unsupported_answer": not support_ok,
        "unusable_citation": not citation_ok,
        "failure_to_abstain": not critical_ok,
        "stale_or_undated_evidence": not freshness_ok,
        "accepted": critical_ok,
        "property_distance_meters": distance,
        "reasons": reasons,
    }


def audit(predictions_document: dict, rows: list[dict] | None = None) -> dict:
    rows = rows or refresh_evidence.load_rows()
    predictions = predictions_document.get("predictions", predictions_document)
    details = [score_item(row, predictions.get(row["id"])) for row in rows]
    error_fields = [
        "wrong_property",
        "wrong_source",
        "unsupported_answer",
        "unusable_citation",
        "failure_to_abstain",
        "stale_or_undated_evidence",
    ]
    counts = {field: sum(bool(item[field]) for item in details) for field in error_fields}
    attempted = sum(item["attempted"] for item in details)
    abstained_count = sum(item["abstained"] for item in details)
    accepted = sum(item["accepted"] for item in details)
    correct = sum(item["answer_correct"] is True for item in details)
    by_task = {}
    for task in sorted({row["task"] for row in rows}):
        items = [item for item in details if item["task"] == task]
        by_task[task] = {
            "items": len(items),
            "attempted": sum(item["attempted"] for item in items),
            "abstained": sum(item["abstained"] for item in items),
            "accepted": sum(item["accepted"] for item in items),
            **{field: sum(item[field] for item in items) for field in error_fields},
        }
    return {
        "schema_version": "2.0",
        "run_id": predictions_document.get("run_id"),
        "condition": predictions_document.get("condition"),
        "model_requested": predictions_document.get("model_requested"),
        "models_returned": predictions_document.get("models_returned"),
        "dataset_sha256": predictions_document.get("dataset_sha256"),
        "summary": {
            "items": len(details),
            "attempted": attempted,
            "abstained": abstained_count,
            "boolean_answers_correct": correct,
            "accepted_answers": accepted,
            "acceptance_rate": accepted / len(details) if details else 0,
            "abstention_rate": abstained_count / len(details) if details else 0,
            "zero_critical_error_pass": sum(counts.values()) == 0,
            **counts,
        },
        "by_task": by_task,
        "details": details,
        "interpretation": "An accepted answer must be correct, tied to the reviewed property, supported by the right official source, cited at record level and current. Abstention avoids a critical error but does not count as an accepted answer.",
    }


def markdown_report(result: dict) -> str:
    summary = result["summary"]
    lines = [
        "# GroundTruth-Geo run audit",
        "",
        f"- Run: `{result.get('run_id')}`",
        f"- Condition: `{result.get('condition')}`",
        f"- Requested model: `{result.get('model_requested')}`",
        f"- Items: {summary['items']}",
        f"- Accepted answers: {summary['accepted_answers']}",
        f"- Abstentions: {summary['abstained']}",
        f"- Zero-critical-error pass: **{'yes' if summary['zero_critical_error_pass'] else 'no'}**",
        "",
        "## Failure counts",
        "",
        "| check | count |",
        "|---|---:|",
    ]
    for field in ["wrong_property", "wrong_source", "unsupported_answer", "unusable_citation", "failure_to_abstain", "stale_or_undated_evidence"]:
        lines.append(f"| {field.replace('_', ' ')} | {summary[field]} |")
    lines.extend(
        [
            "",
            "An abstention avoids a critical error but is not an accepted property answer. An accepted answer must pass all six checks.",
            "",
            "## Item results",
            "",
            "| item | task | attempted | accepted | result |",
            "|---|---|:---:|:---:|---|",
        ]
    )
    for item in result["details"]:
        result_text = "; ".join(item["reasons"]) or "accepted"
        lines.append(f"| {item['item_id']} | {item['task']} | {'yes' if item['attempted'] else 'no'} | {'yes' if item['accepted'] else 'no'} | {result_text} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", help="run directory or predictions.json")
    args = parser.parse_args()
    path = Path(args.run).resolve()
    run_dir = path if path.is_dir() else path.parent
    predictions_path = run_dir / "predictions.json" if path.is_dir() else path
    predictions = json.loads(predictions_path.read_text())
    result = audit(predictions)
    audit_json_path = run_dir / "audit.json"
    audit_markdown_path = run_dir / "audit.md"
    audit_json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    audit_markdown_path.write_text(markdown_report(result))
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        manifest.setdefault("file_sha256", {}).update(
            {
                "audit.json": refresh_evidence.sha256(audit_json_path.read_bytes()),
                "audit.md": refresh_evidence.sha256(audit_markdown_path.read_bytes()),
            }
        )
        manifest["audit_summary"] = result["summary"]
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
