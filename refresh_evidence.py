#!/usr/bin/env python3
"""Refresh and validate record-level evidence for the 33 public cases.

The refresh path uses only public government services. It writes one evidence
record per benchmark item and rewrites the public JSONL only after all 33 cases
pass. The validation path is offline and is suitable for CI.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "groundtruth_geo.jsonl"
EVIDENCE_DIR = ROOT / "evidence" / "records"
USER_AGENT = "GroundTruth-Geo evidence refresh; https://github.com/sulmusic2-star/groundtruth-geo"

CENSUS_GEOCODER = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
FEMA_FLOOD_LAYER = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
NPS_NRHP_POLYGONS = "https://mapservices.nps.gov/arcgis/rest/services/cultural_resources/nrhp_locations/MapServer/1/query"
EPA_ENVIROFACTS_LAYER = "https://geopub.epa.gov/ArcGIS/rest/services/EMEF/efpoints/MapServer/{layer}/query"

EPA_LAYERS = {0: "Superfund", 5: "Brownfields"}
NEARBY_RADIUS_MILES = 0.25

# Census address ranges normalize these two civic landmarks unexpectedly. Each
# exception is narrow, reviewed, and backed by a government page identifying
# the requested landmark. No general fuzzy-address override is allowed.
IDENTITY_EXCEPTIONS = {
    "1 City Hall Sq, Boston, MA": {
        "accepted_match": "1 CITY HALL AVE, BOSTON, MA, 02108",
        "reason": "The Census geocoder resolves Boston City Hall Square to City Hall Avenue.",
        "official_identity_url": "https://www.boston.gov/departments/public-facilities/city-hall",
    },
    "200 N Spring St, Los Angeles, CA": {
        "accepted_match": "200 S SPRING ST, LOS ANGELES, CA, 90012",
        "reason": "The Census range match reverses the street direction; the City of Los Angeles identifies City Hall as 200 N Spring St.",
        "official_identity_url": "https://cityclerk.lacity.org/cal/",
    },
}

TASK_KEYS = {
    "fema_sfha": "in_sfha",
    "historic_district": "in_historic_district",
    "contamination_nearby": "has_nearby_site",
}


class EvidenceError(RuntimeError):
    pass


def canonical_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(value) -> str:
    data = value if isinstance(value, bytes) else canonical_json(value)
    return hashlib.sha256(data).hexdigest()


def load_rows(path: Path = DATASET) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def question_address(row: dict) -> str:
    match = re.search(r'property at "([^"]+)"', row["question"])
    if not match:
        raise EvidenceError(f"{row['id']}: question has no quoted property address")
    return match.group(1)


def request_json(url: str, attempts: int = 8) -> dict:
    last_error = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.load(response)
            if payload.get("error"):
                raise EvidenceError(f"official service error: {payload['error']}")
            return payload
        except Exception as exc:  # government services occasionally reset TLS
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(min(1 + attempt, 6))
    raise EvidenceError(f"request failed after {attempts} attempts: {url}: {last_error}")


def build_url(base: str, params: dict) -> str:
    return base + "?" + urllib.parse.urlencode(params)


def geocode(address: str) -> tuple[str, dict]:
    url = build_url(
        CENSUS_GEOCODER,
        {"address": address, "benchmark": "Public_AR_Current", "format": "json"},
    )
    payload = request_json(url)
    matches = payload.get("result", {}).get("addressMatches", [])
    if len(matches) != 1:
        raise EvidenceError(f"{address}: expected one Census match, got {len(matches)}")
    return url, payload


def identity_record(address: str, geocoder_url: str, payload: dict) -> dict:
    match = payload["result"]["addressMatches"][0]
    matched = match["matchedAddress"]
    exception = IDENTITY_EXCEPTIONS.get(address)
    if exception:
        if matched != exception["accepted_match"]:
            raise EvidenceError(f"{address}: reviewed alias changed to {matched}")
        status = "verified_reviewed_alias"
    else:
        requested_number = re.match(r"^\s*(\d+)", address)
        matched_number = re.match(r"^\s*(\d+)", matched)
        if not requested_number or not matched_number or requested_number.group(1) != matched_number.group(1):
            raise EvidenceError(f"{address}: property number mismatch: {matched}")
        status = "verified_census_match"
    coordinates = match.get("coordinates", {})
    if not isinstance(coordinates.get("x"), (int, float)) or not isinstance(coordinates.get("y"), (int, float)):
        raise EvidenceError(f"{address}: missing Census coordinates")
    return {
        "status": status,
        "requested_address": address,
        "matched_address": matched,
        "longitude": coordinates["x"],
        "latitude": coordinates["y"],
        "geocoder": "United States Census Geocoder",
        "record_url": geocoder_url,
        "response_sha256": sha256(payload),
        "reviewed_exception": exception,
        "raw_response": payload,
    }


def arcgis_point_params(identity: dict, out_fields: str) -> dict:
    return {
        "f": "json",
        "geometry": f"{identity['longitude']},{identity['latitude']}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": out_fields,
        "returnGeometry": "false",
    }


def official_query(source: str, url: str, payload: dict, qualifying_records: list[dict]) -> dict:
    return {
        "source": source,
        "record_url": url,
        "response_sha256": sha256(payload),
        "returned_record_count": len(payload.get("features", [])),
        "qualifying_record_count": len(qualifying_records),
        "qualifying_records": qualifying_records,
        "raw_response": payload,
    }


def refresh_flood(identity: dict) -> tuple[dict, list[dict], dict]:
    params = arcgis_point_params(
        identity,
        "OBJECTID,DFIRM_ID,FLD_AR_ID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,SOURCE_CIT,GFID,GlobalID",
    )
    url = build_url(FEMA_FLOOD_LAYER, params)
    payload = request_json(url)
    records = [feature["attributes"] for feature in payload.get("features", [])]
    if len(records) != 1:
        raise EvidenceError(f"FEMA point query expected one polygon, got {len(records)}")
    record = records[0]
    if record.get("SFHA_TF") not in {"T", "F"} or not record.get("FLD_ZONE"):
        raise EvidenceError(f"FEMA record lacks a usable SFHA flag or zone: {record}")
    answer = {"in_sfha": record["SFHA_TF"] == "T", "zone": record["FLD_ZONE"]}
    rule = {
        "id": "fema-nfhl-point-sfha-v2",
        "plain_language": "The point must intersect one FEMA flood-zone polygon. SFHA_TF=T means yes; SFHA_TF=F means no.",
        "predicate": "feature_count == 1 and SFHA_TF in {'T','F'}",
    }
    return answer, [official_query("FEMA National Flood Hazard Layer", url, payload, records)], rule


def refresh_historic(identity: dict) -> tuple[dict, list[dict], dict]:
    params = arcgis_point_params(
        identity,
        "OBJECTID,NRIS_Refnum,RESNAME,ResType,Address,City,State,CertDate,CR_ID,PROPERTY_ID,STATUS,NARA_URL,EDIT_DATE,SOURCE,SRC_DATE",
    )
    url = build_url(NPS_NRHP_POLYGONS, params)
    payload = request_json(url)
    returned = [feature["attributes"] for feature in payload.get("features", [])]
    districts = [
        record
        for record in returned
        if str(record.get("ResType", "")).lower() == "district"
        and str(record.get("STATUS", "")).lower() == "listed"
    ]
    districts.sort(key=lambda record: (record.get("RESNAME") or "", record.get("NRIS_Refnum") or ""))
    names = [record["RESNAME"] for record in districts]
    answer = {
        "in_historic_district": bool(districts),
        "district": names[0] if len(names) == 1 else ("; ".join(names) if names else None),
        "districts": names,
    }
    rule = {
        "id": "nps-nrhp-listed-district-point-v2",
        "plain_language": "Only intersecting National Register polygons labeled as a listed district count. Buildings, objects, sites and structures do not.",
        "predicate": "lower(ResType) == 'district' and lower(STATUS) == 'listed'",
        "excluded_intersections": [record for record in returned if record not in districts],
    }
    return answer, [official_query("National Park Service National Register polygons", url, payload, districts)], rule


def refresh_cleanup(identity: dict) -> tuple[dict, list[dict], dict]:
    queries = []
    included = []
    for layer, label in EPA_LAYERS.items():
        params = arcgis_point_params(identity, "*")
        params.update(
            {
                "distance": str(NEARBY_RADIUS_MILES),
                "units": "esriSRUnit_StatuteMile",
                "returnGeometry": "true",
                "outSR": "4326",
            }
        )
        url = build_url(EPA_ENVIROFACTS_LAYER.format(layer=layer), params)
        payload = request_json(url)
        records = []
        for feature in payload.get("features", []):
            record = copy.deepcopy(feature.get("attributes", {}))
            record["geometry"] = feature.get("geometry")
            record["program_layer"] = label
            records.append(record)
        queries.append(official_query(f"EPA Envirofacts {label}", url, payload, records))
        included.extend(records)
    unique = {}
    for record in included:
        key = (
            record.get("program_layer"),
            record.get("registry_id"),
            record.get("pgm_sys_id") or record.get("site_id"),
        )
        unique[key] = record
    records = [unique[key] for key in sorted(unique, key=lambda value: tuple(str(part or "") for part in value))]
    answer = {
        "has_nearby_site": bool(records),
        "count": len(records),
        "radius_miles": NEARBY_RADIUS_MILES,
        "programs": sorted(EPA_LAYERS.values()),
    }
    rule = {
        "id": "epa-superfund-brownfields-quarter-mile-v2",
        "plain_language": "Count unique EPA Superfund and Brownfields program records within 0.25 statute mile of the geocoded point.",
        "predicate": "distance_miles <= 0.25 and program_layer in {'Superfund','Brownfields'}",
        "deduplication_key": ["program_layer", "registry_id", "pgm_sys_id_or_site_id"],
    }
    return answer, queries, rule


REFRESHERS = {
    "fema_sfha": refresh_flood,
    "historic_district": refresh_historic,
    "contamination_nearby": refresh_cleanup,
}


def question_for(row: dict) -> str:
    address = question_address(row)
    if row["task"] == "fema_sfha":
        return f'Is the geocoded point for "{address}" in a FEMA Special Flood Hazard Area? Answer yes or no and give the FEMA zone.'
    if row["task"] == "historic_district":
        return f'Is the geocoded point for "{address}" inside a listed National Register historic district? Answer yes or no and name every intersecting district.'
    if row["task"] == "contamination_nearby":
        return f'Are any EPA Superfund or Brownfields program records within 0.25 mile of the geocoded point for "{address}"? Answer yes or no and give the count.'
    raise EvidenceError(f"unknown task: {row['task']}")


def source_summary(task: str) -> tuple[str, str]:
    if task == "fema_sfha":
        return "FEMA National Flood Hazard Layer", FEMA_FLOOD_LAYER.rsplit("/query", 1)[0]
    if task == "historic_district":
        return "National Park Service National Register of Historic Places", NPS_NRHP_POLYGONS.rsplit("/query", 1)[0]
    return "EPA Envirofacts Superfund and Brownfields", "https://geopub.epa.gov/ArcGIS/rest/services/EMEF/efpoints/MapServer"


def refreshed_fingerprint(row: dict) -> str:
    stable = {
        "id": row["id"],
        "task": row["task"],
        "question": row["question"],
        "answer": row["answer"],
        "address": row["address"],
        "record_id": row["record_id"],
        "evidence_sha256": row["evidence_sha256"],
    }
    return sha256(stable)[:16]


def refresh_all(retrieved_at: str) -> tuple[list[dict], list[dict]]:
    rows = load_rows()
    identities = {}
    evidence_records = []
    refreshed_rows = []
    for old in rows:
        address = question_address(old)
        if address not in identities:
            geocoder_url, geocoder_payload = geocode(address)
            identities[address] = identity_record(address, geocoder_url, geocoder_payload)
        identity = identities[address]
        answer, queries, rule = REFRESHERS[old["task"]](identity)
        evidence = {
            "schema_version": "2.0",
            "item_id": old["id"],
            "task": old["task"],
            "retrieved_at": retrieved_at,
            "status": "verified",
            "property_identity": identity,
            "official_queries": queries,
            "derivation_rule": rule,
            "gold_answer": answer,
            "review": {
                "automated_official_source_check": True,
                "independent_human_review": False,
                "note": "Official records were refreshed and derived deterministically; independent review is still pending.",
            },
        }
        evidence_digest = sha256(evidence)
        source, source_url = source_summary(old["task"])
        row = copy.deepcopy(old)
        row.update(
            {
                "schema_version": "2.0",
                "question": question_for(old),
                "answer": answer,
                "source": source,
                "source_url": source_url,
                "source_date": retrieved_at[:10],
                "retrieved_at": retrieved_at,
                "address": identity["requested_address"].upper(),
                "matched_address": identity["matched_address"],
                "longitude": identity["longitude"],
                "latitude": identity["latitude"],
                "evidence_path": f"evidence/records/{old['id']}.json",
                "evidence_sha256": evidence_digest,
                "evidence_status": "verified",
                "independent_review": False,
                "reproducible": True,
            }
        )
        row["fingerprint"] = refreshed_fingerprint(row)
        evidence_records.append(evidence)
        refreshed_rows.append(row)
    return refreshed_rows, evidence_records


def validate(rows: list[dict] | None = None) -> dict:
    rows = rows or load_rows()
    errors = []
    ids = set()
    required = {
        "schema_version",
        "id",
        "task",
        "question",
        "answer",
        "source_url",
        "retrieved_at",
        "record_id",
        "fingerprint",
        "evidence_path",
        "evidence_sha256",
        "evidence_status",
        "independent_review",
    }
    for row in rows:
        missing = required - set(row)
        if missing:
            errors.append(f"{row.get('id')}: missing {sorted(missing)}")
            continue
        if row["id"] in ids:
            errors.append(f"{row['id']}: duplicate id")
        ids.add(row["id"])
        if row["evidence_status"] != "verified":
            errors.append(f"{row['id']}: evidence status is not verified")
        if row["independent_review"] is not False:
            errors.append(f"{row['id']}: public set must not imply independent review")
        if "permit" in row["question"].lower() or "permit" in row["task"].lower():
            errors.append(f"{row['id']}: permit content is out of scope")
        evidence_path = ROOT / row["evidence_path"]
        if not evidence_path.exists():
            errors.append(f"{row['id']}: missing evidence file {row['evidence_path']}")
            continue
        evidence = json.loads(evidence_path.read_text())
        if sha256(evidence) != row["evidence_sha256"]:
            errors.append(f"{row['id']}: evidence digest mismatch")
        if evidence.get("item_id") != row["id"] or evidence.get("gold_answer") != row["answer"]:
            errors.append(f"{row['id']}: evidence answer or id mismatch")
        if not evidence.get("official_queries"):
            errors.append(f"{row['id']}: no official record query")
        for query in evidence.get("official_queries", []):
            if not query.get("record_url", "").startswith("https://"):
                errors.append(f"{row['id']}: non-HTTPS record URL")
            if sha256(query.get("raw_response")) != query.get("response_sha256"):
                errors.append(f"{row['id']}: official response digest mismatch")
        identity = evidence.get("property_identity", {})
        if sha256(identity.get("raw_response")) != identity.get("response_sha256"):
            errors.append(f"{row['id']}: geocoder response digest mismatch")
    expected = {"fema_sfha": 11, "historic_district": 11, "contamination_nearby": 11}
    counts = {task: sum(row.get("task") == task for row in rows) for task in expected}
    if len(rows) != 33 or counts != expected:
        errors.append(f"expected 33 balanced public cases, got {len(rows)} and {counts}")
    if errors:
        raise EvidenceError("\n".join(errors))
    dataset_digest = sha256(DATASET.read_bytes()) if DATASET.exists() else None
    return {
        "status": "passed",
        "items": len(rows),
        "addresses": len({row["address"] for row in rows}),
        "tasks": counts,
        "dataset_sha256": dataset_digest,
        "independent_review": False,
    }


def write_refresh(rows: list[dict], evidence_records: list[dict]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    for evidence in evidence_records:
        path = EVIDENCE_DIR / f"{evidence['item_id']}.json"
        path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")
    DATASET.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="query official services and atomically refresh all 33 public cases")
    parser.add_argument("--validate", action="store_true", help="validate the stored public evidence offline")
    args = parser.parse_args()
    if not args.refresh and not args.validate:
        parser.error("choose --refresh or --validate")
    if args.refresh:
        retrieved_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        rows, evidence_records = refresh_all(retrieved_at)
        # Write to the canonical paths only after every network query succeeded.
        write_refresh(rows, evidence_records)
    result = validate()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
