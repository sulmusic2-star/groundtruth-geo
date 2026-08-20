#!/usr/bin/env python3
"""Gold-blind, second-implementation review for GroundTruth-Geo evidence.

This reviewer deliberately does not import ``refresh_evidence.py`` or the
private holdout builder. It derives each answer from the stored raw government
response before comparing that derivation with the benchmark answer. It also
tests semantic controls with adversarial, internally re-hashed mutations.

The result is a replicated automated review. It is not independent human
review and must never be described as such.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import datetime as dt
import hashlib
import json
import math
import re
import ssl
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PUBLIC_ROOT = Path(__file__).resolve().parent
USER_AGENT = "GroundTruth-Geo replicated evidence reviewer; https://github.com/sulmusic2-star/groundtruth-geo"
MAX_AGE_DAYS = 45
RADIUS_MILES = 0.25

TASK_HOSTS = {
    "fema_sfha": {"hazards.fema.gov"},
    "historic_district": {"mapservices.nps.gov"},
    "contamination_nearby": {"geopub.epa.gov"},
}
TASK_PATHS = {
    "fema_sfha": re.compile(r"/arcgis/rest/services/public/NFHL/MapServer/28/query$", re.I),
    "historic_district": re.compile(
        r"/arcgis/rest/services/cultural_resources/nrhp_locations/MapServer/1/query$", re.I
    ),
    "contamination_nearby": re.compile(
        r"/ArcGIS/rest/services/EMEF/efpoints/MapServer/(0|5)/query$", re.I
    ),
}
IDENTITY_HOSTS = {"geocoding.geo.census.gov", "arcgisserver.digital.mass.gov"}


class ReviewError(RuntimeError):
    """Raised only for an unusable review collection, not a case disagreement."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp lacks a timezone")
    return parsed.astimezone(dt.timezone.utc)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def approximately(left: Any, right: Any, tolerance: float = 1e-9) -> bool:
    return isinstance(left, (int, float)) and isinstance(right, (int, float)) and abs(left - right) <= tolerance


def normalize_address(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(value).upper()).strip()


def haversine_miles(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def add_issue(issues: list[dict], role: str, code: str, detail: str) -> None:
    issues.append({"role": role, "code": code, "detail": detail})


def validate_https_url(
    url: str,
    allowed_hosts: set[str],
    role: str,
    code_prefix: str,
    issues: list[dict],
) -> urllib.parse.ParseResult | None:
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as exc:
        add_issue(issues, role, f"{code_prefix}_url_invalid", str(exc))
        return None
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        add_issue(issues, role, f"{code_prefix}_not_https", url)
    if host not in allowed_hosts:
        add_issue(issues, role, f"{code_prefix}_host_not_allowed", host or "missing host")
    if parsed.username or parsed.password:
        add_issue(issues, role, f"{code_prefix}_contains_credentials", "URL contains user information")
    return parsed


def verify_identity(receipt: dict, issues: list[dict]) -> tuple[float | None, float | None]:
    role = "property_identity"
    identity = receipt.get("property_identity")
    if not isinstance(identity, dict):
        add_issue(issues, role, "identity_missing", "property_identity is missing")
        return None, None
    parsed = validate_https_url(
        str(identity.get("record_url", "")), IDENTITY_HOSTS, role, "identity_source", issues
    )
    raw = identity.get("raw_response")
    if not isinstance(raw, dict):
        add_issue(issues, role, "identity_raw_missing", "raw identity response is missing")
        return None, None
    if canonical_sha256(raw) != identity.get("response_sha256"):
        add_issue(issues, role, "identity_response_hash_mismatch", "stored identity response digest differs")
    if raw.get("error"):
        add_issue(issues, role, "identity_source_error", str(raw.get("error")))

    longitude, latitude = identity.get("longitude"), identity.get("latitude")
    status = identity.get("status")
    if status in {"verified_census_match", "verified_reviewed_alias"}:
        matches = raw.get("result", {}).get("addressMatches", [])
        if len(matches) != 1:
            add_issue(issues, role, "census_match_count", f"expected 1 match; got {len(matches)}")
            return longitude, latitude
        match = matches[0]
        coords = match.get("coordinates", {})
        if not approximately(coords.get("x"), longitude) or not approximately(coords.get("y"), latitude):
            add_issue(issues, role, "identity_coordinate_mismatch", "receipt coordinates differ from raw match")
        if match.get("matchedAddress") != identity.get("matched_address"):
            add_issue(issues, role, "identity_matched_address_mismatch", "matched address differs from raw match")
        requested = str(identity.get("requested_address", ""))
        matched = str(identity.get("matched_address", ""))
        if status == "verified_census_match":
            requested_number = re.match(r"\s*(\d+)", requested)
            matched_number = re.match(r"\s*(\d+)", matched)
            if not requested_number or not matched_number or requested_number.group(1) != matched_number.group(1):
                add_issue(issues, role, "identity_house_number_mismatch", f"{requested} -> {matched}")
        else:
            exception = identity.get("reviewed_exception")
            if not isinstance(exception, dict) or exception.get("accepted_match") != matched:
                add_issue(issues, role, "reviewed_alias_contract_missing", "alias has no exact accepted-match contract")
            else:
                validate_https_url(
                    str(exception.get("official_identity_url", "")),
                    {"www.boston.gov", "boston.gov", "cityclerk.lacity.org"},
                    role,
                    "alias_authority",
                    issues,
                )
    elif status == "verified_massgis_address_point":
        features = raw.get("features", [])
        if len(features) != 1:
            add_issue(issues, role, "massgis_match_count", f"expected 1 address point; got {len(features)}")
            return longitude, latitude
        feature = features[0]
        attrs, geometry = feature.get("attributes", {}), feature.get("geometry", {})
        if not approximately(geometry.get("x"), longitude) or not approximately(geometry.get("y"), latitude):
            add_issue(issues, role, "identity_coordinate_mismatch", "receipt coordinates differ from MassGIS point")
        if attrs.get("OBJECTID") != identity.get("massgis_objectid"):
            add_issue(issues, role, "massgis_objectid_mismatch", "OBJECTID differs from raw point")
        if attrs.get("MASTER_ADDRESS_ID") != identity.get("master_address_id"):
            add_issue(issues, role, "massgis_master_address_mismatch", "MASTER_ADDRESS_ID differs")
        reconstructed = ", ".join(
            part
            for part in [
                f"{attrs.get('FULL_NUMBER_STANDARDIZED', '')} {attrs.get('STREET_NAME', '')}".strip(),
                str(attrs.get("GEOGRAPHIC_TOWN") or "").strip(),
                "MA",
                str(attrs.get("POSTCODE") or "").strip(),
            ]
            if part
        )
        if normalize_address(reconstructed) != normalize_address(identity.get("requested_address", "")):
            add_issue(issues, role, "massgis_address_mismatch", f"{reconstructed} differs from requested address")
        if parsed and not re.search(r"/MassGIS_Master_Address_Points/MapServer/0/query$", parsed.path, re.I):
            add_issue(issues, role, "identity_layer_mismatch", parsed.path)
    else:
        add_issue(issues, role, "identity_status_unknown", str(status))
    return longitude, latitude


def query_features(query: dict, issues: list[dict], index: int) -> list[dict]:
    role = "source_authority"
    raw = query.get("raw_response")
    if not isinstance(raw, dict):
        add_issue(issues, role, "official_raw_missing", f"query {index} has no raw response")
        return []
    if canonical_sha256(raw) != query.get("response_sha256"):
        add_issue(issues, role, "official_response_hash_mismatch", f"query {index}")
    if raw.get("error"):
        add_issue(issues, role, "official_source_error", f"query {index}: {raw.get('error')}")
        return []
    features = raw.get("features")
    if not isinstance(features, list):
        add_issue(issues, role, "official_features_missing", f"query {index}")
        return []
    if query.get("returned_record_count") != len(features):
        add_issue(
            issues,
            role,
            "returned_count_mismatch",
            f"query {index}: stored {query.get('returned_record_count')}; raw {len(features)}",
        )
    return features


def verify_query_contract(
    task: str,
    query: dict,
    index: int,
    longitude: float | None,
    latitude: float | None,
    issues: list[dict],
) -> tuple[urllib.parse.ParseResult | None, list[dict]]:
    role = "source_authority"
    parsed = validate_https_url(
        str(query.get("record_url", "")), TASK_HOSTS[task], role, "official_source", issues
    )
    if parsed and not TASK_PATHS[task].search(parsed.path):
        add_issue(issues, role, "official_layer_mismatch", f"query {index}: {parsed.path}")
    if parsed:
        params = urllib.parse.parse_qs(parsed.query)
        geometry = (params.get("geometry") or [""])[0]
        try:
            query_lon, query_lat = (float(part) for part in geometry.split(","))
            if not approximately(query_lon, longitude) or not approximately(query_lat, latitude):
                add_issue(issues, "property_identity", "query_point_mismatch", f"query {index}: {geometry}")
        except Exception:
            add_issue(issues, "property_identity", "query_point_missing", f"query {index}: {geometry!r}")
        if (params.get("geometryType") or [""])[0] != "esriGeometryPoint":
            add_issue(issues, role, "query_geometry_type_mismatch", f"query {index}")
        if (params.get("spatialRel") or [""])[0] != "esriSpatialRelIntersects":
            add_issue(issues, role, "query_spatial_relation_mismatch", f"query {index}")
        if task == "contamination_nearby":
            if (params.get("distance") or [""])[0] != "0.25":
                add_issue(issues, role, "cleanup_radius_mismatch", f"query {index}")
            if (params.get("units") or [""])[0] != "esriSRUnit_StatuteMile":
                add_issue(issues, role, "cleanup_units_mismatch", f"query {index}")
    return parsed, query_features(query, issues, index)


def derive_fema(features_by_query: list[tuple[dict, urllib.parse.ParseResult | None, list[dict]]], issues: list[dict]) -> dict | None:
    role = "domain_derivation"
    if len(features_by_query) != 1:
        add_issue(issues, role, "fema_query_count", f"expected 1 query; got {len(features_by_query)}")
        return None
    features = features_by_query[0][2]
    if len(features) != 1:
        add_issue(issues, role, "fema_polygon_count", f"expected 1 polygon; got {len(features)}")
        return None
    attrs = features[0].get("attributes", {})
    flag, zone = attrs.get("SFHA_TF"), attrs.get("FLD_ZONE")
    if flag not in {"T", "F"} or not zone:
        add_issue(issues, role, "fema_answer_unusable", f"flag={flag!r}, zone={zone!r}")
        return None
    return {"in_sfha": flag == "T", "zone": zone}


def derive_historic(features_by_query: list[tuple[dict, urllib.parse.ParseResult | None, list[dict]]], issues: list[dict]) -> dict | None:
    role = "domain_derivation"
    if len(features_by_query) != 1:
        add_issue(issues, role, "historic_query_count", f"expected 1 query; got {len(features_by_query)}")
        return None
    records = [feature.get("attributes", {}) for feature in features_by_query[0][2]]
    qualifying = [
        record
        for record in records
        if str(record.get("ResType", "")).strip().lower() == "district"
        and str(record.get("STATUS", "")).strip().lower() == "listed"
    ]
    qualifying.sort(key=lambda record: (str(record.get("RESNAME") or ""), str(record.get("NRIS_Refnum") or "")))
    names = [record.get("RESNAME") for record in qualifying]
    if any(not name for name in names):
        add_issue(issues, role, "historic_name_missing", "a qualifying listed district has no name")
        return None
    return {
        "in_historic_district": bool(names),
        "district": names[0] if len(names) == 1 else ("; ".join(names) if names else None),
        "districts": names,
    }


def derive_cleanup(
    features_by_query: list[tuple[dict, urllib.parse.ParseResult | None, list[dict]]],
    longitude: float | None,
    latitude: float | None,
    issues: list[dict],
) -> dict | None:
    role = "domain_derivation"
    if len(features_by_query) != 2:
        add_issue(issues, role, "cleanup_query_count", f"expected 2 program queries; got {len(features_by_query)}")
        return None
    unique: dict[tuple, dict] = {}
    seen_layers = set()
    for _, parsed, features in features_by_query:
        match = re.search(r"/MapServer/(0|5)/query$", parsed.path, re.I) if parsed else None
        if not match:
            continue
        layer = match.group(1)
        program = {"0": "Superfund", "5": "Brownfields"}[layer]
        seen_layers.add(program)
        for feature in features:
            attrs = copy.deepcopy(feature.get("attributes", {}))
            geometry = feature.get("geometry") or {}
            if not all(isinstance(geometry.get(axis), (int, float)) for axis in ("x", "y")):
                add_issue(issues, role, "cleanup_geometry_missing", f"{program} record lacks point geometry")
                continue
            if not isinstance(longitude, (int, float)) or not isinstance(latitude, (int, float)):
                add_issue(issues, role, "cleanup_property_point_missing", "property coordinates unavailable")
                continue
            distance = haversine_miles(longitude, latitude, geometry["x"], geometry["y"])
            if distance > RADIUS_MILES + 0.00001:
                add_issue(issues, role, "cleanup_record_outside_radius", f"{distance:.6f} miles")
                continue
            key = (program, attrs.get("registry_id"), attrs.get("pgm_sys_id") or attrs.get("site_id"))
            if not key[1] or not key[2]:
                add_issue(issues, role, "cleanup_record_key_missing", str(key))
                continue
            unique[key] = attrs
    if seen_layers != {"Superfund", "Brownfields"}:
        add_issue(issues, role, "cleanup_program_coverage", f"queried {sorted(seen_layers)}")
        return None
    return {
        "has_nearby_site": bool(unique),
        "count": len(unique),
        "radius_miles": RADIUS_MILES,
        "programs": ["Brownfields", "Superfund"],
    }


def expected_qualifying_records(task: str, parsed: urllib.parse.ParseResult | None, features: list[dict]) -> list[dict]:
    if task == "fema_sfha":
        return [feature.get("attributes", {}) for feature in features]
    if task == "historic_district":
        records = [
            feature.get("attributes", {})
            for feature in features
            if str(feature.get("attributes", {}).get("ResType", "")).strip().lower() == "district"
            and str(feature.get("attributes", {}).get("STATUS", "")).strip().lower() == "listed"
        ]
        records.sort(key=lambda record: (str(record.get("RESNAME") or ""), str(record.get("NRIS_Refnum") or "")))
        return records
    match = re.search(r"/MapServer/(0|5)/query$", parsed.path, re.I) if parsed else None
    program = {"0": "Superfund", "5": "Brownfields"}.get(match.group(1) if match else "")
    records = []
    for feature in features:
        record = copy.deepcopy(feature.get("attributes", {}))
        record["geometry"] = feature.get("geometry")
        record["program_layer"] = program
        records.append(record)
    return records


def verify_freshness(receipt: dict, now: dt.datetime, max_age_days: int, issues: list[dict]) -> None:
    role = "freshness"
    try:
        retrieved = parse_utc(str(receipt.get("retrieved_at", "")))
    except Exception as exc:
        add_issue(issues, role, "retrieval_timestamp_invalid", str(exc))
        return
    age = (now - retrieved).total_seconds() / 86400
    if age < -0.01:
        add_issue(issues, role, "retrieval_timestamp_future", f"age={age:.2f} days")
    if age > max_age_days:
        add_issue(issues, role, "evidence_stale", f"age={age:.1f} days; limit={max_age_days}")


def review_case(case: dict, receipt: dict, now: dt.datetime, max_age_days: int = MAX_AGE_DAYS) -> dict:
    """Review one case. The answer is intentionally read only after derivation."""
    issues: list[dict] = []
    item_id, task = case.get("id"), case.get("task")
    if task not in TASK_HOSTS:
        add_issue(issues, "case_contract", "task_unknown", str(task))
        return {"id": item_id, "task": task, "status": "unresolved", "issues": issues}
    if receipt.get("item_id") != item_id:
        add_issue(issues, "case_contract", "item_id_mismatch", f"{receipt.get('item_id')} != {item_id}")
    if receipt.get("task", task) != task:
        add_issue(issues, "case_contract", "task_mismatch", f"{receipt.get('task')} != {task}")
    if receipt.get("status") != "verified":
        add_issue(issues, "case_contract", "evidence_not_verified", str(receipt.get("status")))
    if canonical_sha256(receipt) != case.get("evidence_sha256"):
        add_issue(issues, "integrity", "evidence_envelope_hash_mismatch", "receipt differs from case commitment")

    longitude, latitude = verify_identity(receipt, issues)
    queries = receipt.get("official_queries")
    if not isinstance(queries, list) or not queries:
        add_issue(issues, "source_authority", "official_queries_missing", "no official record queries")
        queries = []
    reviewed_queries = []
    for index, query in enumerate(queries):
        if not isinstance(query, dict):
            add_issue(issues, "source_authority", "official_query_invalid", f"query {index}")
            continue
        parsed, features = verify_query_contract(task, query, index, longitude, latitude, issues)
        expected_records = expected_qualifying_records(task, parsed, features)
        if query.get("qualifying_record_count") != len(expected_records):
            add_issue(
                issues,
                "domain_derivation",
                "qualifying_count_mismatch",
                f"query {index}: stored {query.get('qualifying_record_count')}; derived {len(expected_records)}",
            )
        if query.get("qualifying_records") != expected_records:
            add_issue(issues, "domain_derivation", "qualifying_records_mismatch", f"query {index}")
        reviewed_queries.append((query, parsed, features))

    if task == "fema_sfha":
        derived = derive_fema(reviewed_queries, issues)
    elif task == "historic_district":
        derived = derive_historic(reviewed_queries, issues)
    else:
        derived = derive_cleanup(reviewed_queries, longitude, latitude, issues)

    # Gold is revealed only here, after the raw-response derivation is complete.
    stored_answer = case.get("answer")
    if derived is None:
        add_issue(issues, "answer_adjudication", "answer_unresolved", "raw evidence cannot support yes or no")
    elif derived != stored_answer:
        add_issue(
            issues,
            "answer_adjudication",
            "derived_answer_disagrees",
            f"derived={json.dumps(derived, sort_keys=True)} stored={json.dumps(stored_answer, sort_keys=True)}",
        )
    if receipt.get("gold_answer") != stored_answer:
        add_issue(issues, "integrity", "receipt_gold_disagrees", "receipt gold differs from case answer")
    verify_freshness(receipt, now, max_age_days, issues)

    role_counts = Counter(issue["role"] for issue in issues)
    return {
        "id": item_id,
        "task": task,
        "status": "passed" if not issues else "unresolved",
        "gold_hidden_during_derivation": True,
        "derived_answer": derived,
        "stored_answer": stored_answer,
        "property": {
            "requested_address": receipt.get("property_identity", {}).get("requested_address"),
            "matched_address": receipt.get("property_identity", {}).get("matched_address"),
        },
        "official_query_count": len(reviewed_queries),
        "roles": {
            role: "passed" if role_counts[role] == 0 else "failed"
            for role in (
                "case_contract",
                "integrity",
                "property_identity",
                "source_authority",
                "domain_derivation",
                "answer_adjudication",
                "freshness",
            )
        },
        "issues": issues,
    }


def false_answer(task: str, original: dict) -> dict:
    if task == "fema_sfha":
        return {"in_sfha": False, "zone": original.get("zone") or "X"}
    if task == "historic_district":
        return {"in_historic_district": False, "district": None, "districts": []}
    return {"has_nearby_site": False, "count": 0, "radius_miles": 0.25, "programs": ["Brownfields", "Superfund"]}


def flipped_answer(task: str, answer: dict) -> dict:
    if task == "fema_sfha":
        return {"in_sfha": not bool(answer.get("in_sfha")), "zone": answer.get("zone")}
    if task == "historic_district":
        if answer.get("in_historic_district"):
            return {"in_historic_district": False, "district": None, "districts": []}
        return {"in_historic_district": True, "district": "Invented District", "districts": ["Invented District"]}
    count = int(answer.get("count", 0))
    return {
        "has_nearby_site": not bool(answer.get("has_nearby_site")),
        "count": 0 if count else 1,
        "radius_miles": 0.25,
        "programs": ["Brownfields", "Superfund"],
    }


def rehash_case(case: dict, receipt: dict) -> None:
    case["evidence_sha256"] = canonical_sha256(receipt)


def replace_query_param(url: str, key: str, value: str) -> str:
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    params[key] = [value]
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(params, doseq=True)))


def adversarial_variants(case: dict, receipt: dict) -> list[tuple[str, dict, dict]]:
    variants = []

    mutated_case, mutated_receipt = copy.deepcopy(case), copy.deepcopy(receipt)
    mutated_receipt["official_queries"][0]["record_url"] = "https://example.com/query?geometry=0%2C0"
    rehash_case(mutated_case, mutated_receipt)
    variants.append(("wrong_source_domain", mutated_case, mutated_receipt))

    mutated_case, mutated_receipt = copy.deepcopy(case), copy.deepcopy(receipt)
    identity = mutated_receipt["property_identity"]
    shifted = f"{float(identity['longitude']) + 0.05},{float(identity['latitude']) + 0.05}"
    mutated_receipt["official_queries"][0]["record_url"] = replace_query_param(
        mutated_receipt["official_queries"][0]["record_url"], "geometry", shifted
    )
    rehash_case(mutated_case, mutated_receipt)
    variants.append(("wrong_query_point", mutated_case, mutated_receipt))

    mutated_case, mutated_receipt = copy.deepcopy(case), copy.deepcopy(receipt)
    mutated_receipt["retrieved_at"] = "2020-01-01T00:00:00Z"
    rehash_case(mutated_case, mutated_receipt)
    variants.append(("stale_evidence", mutated_case, mutated_receipt))

    mutated_case, mutated_receipt = copy.deepcopy(case), copy.deepcopy(receipt)
    mutated_receipt["property_identity"]["longitude"] = float(mutated_receipt["property_identity"]["longitude"]) + 0.05
    rehash_case(mutated_case, mutated_receipt)
    variants.append(("wrong_property_coordinate", mutated_case, mutated_receipt))

    mutated_case, mutated_receipt = copy.deepcopy(case), copy.deepcopy(receipt)
    query = mutated_receipt["official_queries"][0]
    query["returned_record_count"] = int(query.get("returned_record_count", 0)) + 1
    rehash_case(mutated_case, mutated_receipt)
    variants.append(("wrong_returned_count", mutated_case, mutated_receipt))

    mutated_case, mutated_receipt = copy.deepcopy(case), copy.deepcopy(receipt)
    query = mutated_receipt["official_queries"][0]
    query["qualifying_records"] = [] if query.get("qualifying_records") else [{"invented": True}]
    query["qualifying_record_count"] = len(query["qualifying_records"])
    rehash_case(mutated_case, mutated_receipt)
    variants.append(("wrong_qualifying_records", mutated_case, mutated_receipt))

    mutated_case, mutated_receipt = copy.deepcopy(case), copy.deepcopy(receipt)
    mutated_case["answer"] = flipped_answer(case["task"], case["answer"])
    variants.append(("wrong_gold_answer", mutated_case, mutated_receipt))

    mutated_case, mutated_receipt = copy.deepcopy(case), copy.deepcopy(receipt)
    query = mutated_receipt["official_queries"][0]
    query["raw_response"] = {"error": {"code": 503, "message": "synthetic service failure"}}
    query["response_sha256"] = canonical_sha256(query["raw_response"])
    query["returned_record_count"] = 0
    query["qualifying_record_count"] = 0
    query["qualifying_records"] = []
    mutated_case["answer"] = false_answer(case["task"], case["answer"])
    mutated_receipt["gold_answer"] = mutated_case["answer"]
    rehash_case(mutated_case, mutated_receipt)
    variants.append(("unknown_forced_to_no", mutated_case, mutated_receipt))
    return variants


def run_adversarial(cases_and_receipts: list[tuple[dict, dict]], now: dt.datetime) -> dict:
    by_variant = defaultdict(lambda: {"attempted": 0, "detected": 0, "missed_case_ids": []})
    for case, receipt in cases_and_receipts:
        for name, mutated_case, mutated_receipt in adversarial_variants(case, receipt):
            result = review_case(mutated_case, mutated_receipt, now)
            bucket = by_variant[name]
            bucket["attempted"] += 1
            if result["status"] == "unresolved":
                bucket["detected"] += 1
            else:
                bucket["missed_case_ids"].append(case["id"])
    attempted = sum(bucket["attempted"] for bucket in by_variant.values())
    detected = sum(bucket["detected"] for bucket in by_variant.values())
    return {
        "attempted": attempted,
        "detected": detected,
        "detection_rate": detected / attempted if attempted else None,
        "variants": dict(sorted(by_variant.items())),
    }


def fetch_json(url: str, attempts: int = 3) -> dict:
    last = None
    context = ssl.create_default_context()
    for _ in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=60, context=context) as response:
                return json.load(response)
        except Exception as exc:
            last = exc
    raise ReviewError(str(last))


def replay_one(entry: tuple[str, str]) -> dict:
    url, expected_sha = entry
    try:
        payload = fetch_json(url)
        observed_sha = canonical_sha256(payload)
        return {
            "url_sha256": hashlib.sha256(url.encode()).hexdigest(),
            "status": "unchanged" if observed_sha == expected_sha else "changed",
            "expected_response_sha256": expected_sha,
            "observed_response_sha256": observed_sha,
            "source_error": payload.get("error"),
        }
    except Exception as exc:
        return {
            "url_sha256": hashlib.sha256(url.encode()).hexdigest(),
            "status": "unavailable",
            "error": f"{type(exc).__name__}: {exc}",
        }


def live_replay(cases_and_receipts: list[tuple[dict, dict]], concurrency: int) -> dict:
    unique = {}
    for _, receipt in cases_and_receipts:
        identity = receipt.get("property_identity", {})
        if identity.get("record_url") and identity.get("response_sha256"):
            unique[identity["record_url"]] = identity["response_sha256"]
        for query in receipt.get("official_queries", []):
            if query.get("record_url") and query.get("response_sha256"):
                unique[query["record_url"]] = query["response_sha256"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
        results = list(executor.map(replay_one, sorted(unique.items())))
    counts = Counter(result["status"] for result in results)
    return {
        "urls": len(results),
        "counts": dict(sorted(counts.items())),
        "all_unchanged": counts.get("unchanged", 0) == len(results),
        "results": results,
    }


def load_collection(root: Path, dataset: Path) -> list[tuple[dict, dict]]:
    cases = load_jsonl(dataset)
    loaded = []
    for case in cases:
        path = root / case["evidence_path"]
        if not path.exists():
            raise ReviewError(f"missing evidence for {case.get('id')}: {path}")
        loaded.append((case, json.loads(path.read_text())))
    return loaded


def aggregate_review(
    collection_name: str,
    dataset: Path,
    cases_and_receipts: list[tuple[dict, dict]],
    live: bool,
    live_concurrency: int,
) -> dict:
    reviewed_at = utc_now()
    now = parse_utc(reviewed_at)
    cases = [review_case(case, receipt, now) for case, receipt in cases_and_receipts]
    status_counts = Counter(case["status"] for case in cases)
    task_counts = Counter(case["task"] for case in cases)
    task_passed = Counter(case["task"] for case in cases if case["status"] == "passed")
    issue_counts = Counter(issue["code"] for case in cases for issue in case["issues"])
    report = {
        "schema_version": "groundtruth_geo_replicated_review.v1",
        "collection": collection_name,
        "reviewed_at": reviewed_at,
        "review_status": "multi_method_replicated_not_independent_human",
        "independent_human_review": False,
        "gold_hidden_during_derivation": True,
        "reviewer_implementation": "replicated_review.py; no imports from evidence generator or holdout builder",
        "data": {
            "dataset_name": dataset.name,
            "dataset_sha256": file_sha256(dataset),
            "cases": len(cases),
            "task_counts": dict(sorted(task_counts.items())),
        },
        "results": {
            "status_counts": dict(sorted(status_counts.items())),
            "task_passed": dict(sorted(task_passed.items())),
            "agreement_rate": status_counts.get("passed", 0) / len(cases) if cases else None,
            "issue_counts": dict(sorted(issue_counts.items())),
        },
        "adversarial": run_adversarial(cases_and_receipts, now),
        "limitations": [
            "This is a second implementation and multi-role automated review, not an independent human review.",
            "The same project owner controls the benchmark and review code; organizational independence is absent.",
            "SHA-256 commitments reveal later changes but are not government digital signatures and cannot prove the original response was never fabricated.",
            "Point-based answers do not replace parcel, boundary, regulatory, legal, engineering, lending, or professional determinations.",
            "The reviewed cases are stratified benchmark cases, not a representative estimate of national or statewide field accuracy.",
        ],
        "cases": cases,
    }
    report["live_replay"] = (
        live_replay(cases_and_receipts, live_concurrency)
        if live
        else {"status": "not_run", "reason": "run with --live-replay to re-fetch every unique government URL"}
    )
    return report


def public_safe_receipt(report: dict) -> dict:
    detailed_digest = canonical_sha256(report)
    return {
        "schema_version": "groundtruth_geo_replicated_review_receipt.v1",
        "collection": report["collection"],
        "reviewed_at": report["reviewed_at"],
        "review_status": report["review_status"],
        "independent_human_review": False,
        "gold_hidden_during_derivation": True,
        "data": report["data"],
        "results": report["results"],
        "adversarial": {
            "attempted": report["adversarial"]["attempted"],
            "detected": report["adversarial"]["detected"],
            "detection_rate": report["adversarial"]["detection_rate"],
            "variants": {
                name: {"attempted": value["attempted"], "detected": value["detected"]}
                for name, value in report["adversarial"]["variants"].items()
            },
        },
        "live_replay": {
            key: value
            for key, value in report["live_replay"].items()
            if key in {"status", "reason", "urls", "counts", "all_unchanged"}
        },
        "detailed_review_sha256": detailed_digest,
        "claim_boundary": "Replicated automated review; not independent human review or representative accuracy proof.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", choices=("public", "private"), default="public")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-safe-output", type=Path)
    parser.add_argument("--live-replay", action="store_true")
    parser.add_argument("--live-concurrency", type=int, default=4)
    args = parser.parse_args()

    if args.root:
        root = args.root.resolve()
    elif args.collection == "public":
        root = PUBLIC_ROOT
    else:
        parser.error("--root is required for a private collection")
    dataset = (args.dataset or (root / ("groundtruth_geo.jsonl" if args.collection == "public" else "cases/gold.jsonl"))).resolve()
    loaded = load_collection(root, dataset)
    report = aggregate_review(args.collection, dataset, loaded, args.live_replay, args.live_concurrency)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    if args.collection == "private":
        args.output.chmod(0o600)
    if args.public_safe_output:
        receipt = public_safe_receipt(report)
        args.public_safe_output.parent.mkdir(parents=True, exist_ok=True)
        args.public_safe_output.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "collection": report["collection"],
                "review_status": report["review_status"],
                "independent_human_review": False,
                "cases": report["data"]["cases"],
                "results": report["results"],
                "adversarial": {
                    "attempted": report["adversarial"]["attempted"],
                    "detected": report["adversarial"]["detected"],
                    "detection_rate": report["adversarial"]["detection_rate"],
                },
                "live_replay": {
                    key: value
                    for key, value in report["live_replay"].items()
                    if key in {"status", "reason", "urls", "counts", "all_unchanged"}
                },
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0 if report["results"]["status_counts"].get("unresolved", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
