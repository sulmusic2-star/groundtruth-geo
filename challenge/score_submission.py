#!/usr/bin/env python3
"""Validate, freeze, and privately score a GroundTruth-Geo blind submission."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

try:
    from .common import canonical_json, digest_file, sha256, utc_now, validate_submission, write_private
except ImportError:
    from common import canonical_json, digest_file, sha256, utc_now, validate_submission, write_private


TASK_KEY = {
    "fema_sfha": "in_sfha",
    "historic_district": "in_historic_district",
    "contamination_nearby": "has_nearby_site",
}
OFFICIAL_HOSTS = {
    "fema_sfha": {"hazards.fema.gov", "msc.fema.gov"},
    "historic_district": {"mapservices.nps.gov", "catalog.archives.gov"},
    "contamination_nearby": {"geopub.epa.gov", "enviro.epa.gov"},
}


def parse_time(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def distance_meters(lon1, lat1, lon2, lat2):
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def normalized_record_url(value: str) -> str:
    parsed = urlparse(value)
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", query, ""))


def known_record_ids(evidence: dict) -> set[str]:
    result = set()
    identity_fields = {
        "OBJECTID", "GlobalID", "GLOBALID", "GFID", "FLD_AR_ID", "CR_ID",
        "PROPERTY_ID", "NRIS_Refnum", "registry_id", "pgm_sys_id", "site_id",
    }
    for query in evidence.get("official_queries", []):
        for record in query.get("qualifying_records", []):
            for key in identity_fields:
                value = record.get(key)
                if value not in (None, ""):
                    result.add(str(value).strip().lower())
    return result


def score(item: dict, prediction: dict) -> dict:
    gold = item["gold"]
    evidence = json.loads(Path(item["evidence_path"]).read_text())
    attempted = prediction.get("attempted") is True and prediction.get("answer") is not None
    if not attempted:
        return {"item_id": item["item_id"], "task": gold["task"], "attempted": False, "accepted": False, "errors": [], "reason": "abstained"}
    identity = evidence["property_identity"]
    requested_ok = str(prediction.get("requested_address", "")).strip().upper() == str(identity["requested_address"]).strip().upper()
    matched_ok = str(prediction.get("matched_address", "")).strip().upper() == str(identity["matched_address"]).strip().upper()
    coordinate_distance = None
    try:
        coordinate_distance = distance_meters(float(prediction["longitude"]), float(prediction["latitude"]), float(identity["longitude"]), float(identity["latitude"]))
    except (TypeError, ValueError):
        pass
    property_ok = requested_ok and matched_ok and coordinate_distance is not None and coordinate_distance <= 25.0
    sources = [source for source in prediction.get("sources", []) if isinstance(source, dict)]
    official_source = any(urlparse(str(source.get("url", ""))).hostname in OFFICIAL_HOSTS[gold["task"]] for source in sources)
    accepted_urls = {normalized_record_url(query["record_url"]) for query in evidence["official_queries"]}
    accepted_record_ids = known_record_ids(evidence)
    usable = [
        source for source in sources
        if source.get("supports_answer") is True
        and (
            normalized_record_url(str(source.get("url", ""))) in accepted_urls
            or str(source.get("record_id", "")).strip().lower() in accepted_record_ids
        )
    ]
    citation_ok = bool(usable)
    gold_time = parse_time(gold["retrieved_at"])
    freshness_ok = bool(gold_time and any((source_time := parse_time(source.get("retrieved_at"))) and source_time >= gold_time for source in usable))
    answer_ok = bool(prediction["answer"]) == bool(gold["answer"][TASK_KEY[gold["task"]]])
    errors = []
    if not property_ok: errors.append("wrong_property")
    if not official_source: errors.append("wrong_source")
    if not citation_ok: errors.append("unusable_citation")
    if not freshness_ok: errors.append("stale_or_undated_evidence")
    if not (answer_ok and property_ok and official_source and citation_ok): errors.append("unsupported_answer")
    if errors or not answer_ok: errors.append("failure_to_abstain")
    return {
        "item_id": item["item_id"],
        "task": gold["task"],
        "attempted": True,
        "answer_correct": answer_ok,
        "accepted": not errors,
        "coordinate_distance_meters": coordinate_distance,
        "errors": sorted(set(errors)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    document = json.loads(args.submission.read_text())
    expected = {item["item_id"] for item in manifest["items"]}
    errors = validate_submission(document, expected)
    if document.get("challenge_id") != manifest["challenge_id"]:
        errors.append("submission challenge_id does not match manifest")
    if errors:
        print(json.dumps({"status": "rejected", "errors": errors}, indent=2))
        return 2
    predictions = {item["item_id"]: item for item in document["predictions"]}
    details = [score(item, predictions[item["item_id"]]) for item in manifest["items"]]
    error_counts = Counter(error for item in details for error in item["errors"])
    summary = {
        "items": len(details),
        "attempted": sum(item["attempted"] for item in details),
        "abstained": sum(not item["attempted"] for item in details),
        "accepted": sum(item["accepted"] for item in details),
        "answer_correct": sum(item.get("answer_correct") is True for item in details),
        "error_counts": dict(sorted(error_counts.items())),
    }
    scored_at = utc_now()
    report = {
        "schema_version": "groundtruth_geo_blind_score.v1",
        "challenge_id": manifest["challenge_id"],
        "scored_at": scored_at,
        "submission_sha256": digest_file(args.submission),
        "participant": document["participant"],
        "run": document["run"],
        "summary": summary,
        "details": details,
        "independent_professional_review": False,
    }
    write_private(args.private_output, report)
    receipt = {
        "schema_version": "groundtruth_geo_blind_score_receipt.v1",
        "challenge_id": manifest["challenge_id"],
        "scored_at": scored_at,
        "submission_sha256": report["submission_sha256"],
        "participant": document["participant"],
        "summary": summary,
        "detailed_score_sha256": sha256(report),
        "independence_status": "external_result_not_professional_review_unless_signed_attestation_is_present",
    }
    args.receipt_output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_output.write_bytes(canonical_json(receipt) + b"\n")
    print(json.dumps({"status": "scored", "summary": summary, "receipt": str(args.receipt_output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
