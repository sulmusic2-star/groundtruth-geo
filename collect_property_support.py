#!/usr/bin/env python3
"""Collect official local property geometry for coordinate-sensitive public cases.

This does not replace the benchmark's Census-geocoded point.  It creates a
parallel property-support record that can show when a locally maintained
address point, building footprint, or parcel changes the screening question.
Only sources marked safe for public redistribution are stored here.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import requests
from pyproj import Geod
from shapely.geometry import Point, shape


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "property_support" / "records"
GEOD = Geod(ellps="WGS84")


class PropertySupportError(RuntimeError):
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


SOURCES = {
    "miami_beach": {
        "address": "1300 OCEAN DR, MIAMI BEACH, FL",
        "address_query": {
            "agency": "Miami-Dade County",
            "dataset": "GeoAddress",
            "url": "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/GeoAddress_gdb/FeatureServer/0",
            "where": "HSE_NUM = '1300' AND ST_NAME = 'OCEAN' AND ST_TYPE = 'DR' AND MUNIC_NAME = 'MIAMI BEACH'",
            "fields": "OBJECTID,ADDRESSID,FOLIO,HSE_NUM,PRE_DIR,ST_NAME,ST_TYPE,SUF_DIR,ZIP,MUNIC_NAME,GlobalID",
        },
        "building_query": {
            "agency": "Miami-Dade County",
            "dataset": "Building Footprint UBID Folio",
            "url": "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/BuildingFootprintUBIDFolio_gdb/FeatureServer/0",
            "where": "ADDRESS = '1300 OCEAN DR' AND CITY = 'Miami Beach'",
            "fields": "OBJECTID,UBID,UNIQUEID,FOLIO,ADDRESS,CITY,ZIP_CODE,SOURCE,TYPE,YEAR_BUILT,GlobalID",
            "address_field": "ADDRESS",
            "expected_address": "1300 OCEAN DR",
        },
        "currency_note": "Current county service; record modification time is not exposed by this layer.",
    },
    "savannah": {
        "address": "10 E LIBERTY ST, SAVANNAH, GA",
        "parcel_query": {
            "agency": "SAGIS and Chatham County Board of Assessors",
            "dataset": "Property Boundaries (Parcels)",
            "url": "https://sagisservices.sagis.org/arcgis/rest/services/SAGISorg/MapLayers/MapServer/4",
            "where": "PropAddress_Num = '10' AND PropAddress_PreDir = 'E' AND PropAddress_StreetName = 'LIBERTY' AND PropAddress_StreetType = 'ST'",
            "fields": "OBJECTID,PIN,PropAddress_Full,Date_Updated",
        },
        "restricted_source": {
            "url": "https://pub.sagis.org/arcgis/rest/services/Savannah/PersonalCareHomeMap/MapServer/11",
            "reason": "The service description says do not distribute and requires a data sharing agreement; it is not collected or republished.",
        },
        "currency_note": "The public parcel service is usable for public verification; the more detailed master address layer is deliberately excluded because of its stated redistribution restriction.",
    },
    "austin": {
        "address": "600 CONGRESS AVE, AUSTIN, TX",
        "address_query": {
            "agency": "City of Austin Communications and Technology Management / 9-1-1 Addressing",
            "dataset": "LOCATION address points",
            "url": "https://services.arcgis.com/0L95CJ0VTaxqcmED/arcgis/rest/services/LOCATION_address_points/FeatureServer/0",
            "where": "ADDRESS = 600 AND STREET_NAME = 'CONGRESS' AND STREET_TYPE = 'AVE' AND ADDRESS_FRACTION IS NULL",
            "fields": "OBJECTID,ADDRESS,ADDRESS_FRACTION,ADDRESS_SUFFIX,FULL_STREET_NAME,ADDRESS_TYPE,PLACE_ID,MODIFIED_DATE",
        },
        "building_query": {
            "agency": "City of Austin",
            "dataset": "STRUCTURE building footprints 2017",
            "url": "https://services.arcgis.com/0L95CJ0VTaxqcmED/arcgis/rest/services/UTILITIESCOMMUNICATION_building_footprints_2017/FeatureServer/0",
            "where": "1=1",
            "fields": "OBJECTID,IMPERVIOUS_COVER_ID,PARENT_FEATURE_ID,SOURCE,FEATURE,MODIFIED_DATE,MAX_HEIGHT",
            "spatial_from_address": True,
        },
        "currency_note": "The exact address point is current, but the public building geometry is derived from 2017 imagery; it is provisional for present-day building extent.",
        "requires_currency_review": True,
    },
    "washington_dc": {
        "address": "1600 PENNSYLVANIA AVE NW, WASHINGTON, DC",
        "address_query": {
            "agency": "District of Columbia GIS",
            "dataset": "Address Points",
            "url": "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Location_WebMercator/FeatureServer/0",
            "where": "ADDRESS = '1600 PENNSYLVANIA AVENUE NW' AND STATUS = 'ACTIVE'",
            "fields": "OBJECTID,ADDRESS,STATUS,SSL,PLACEMENT,BUILDING,MAR_ID,LATITUDE,LONGITUDE,LAST_EDITED_DATE",
        },
        "building_query": {
            "agency": "District of Columbia GIS",
            "dataset": "Building Footprints",
            "url": "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Facility_and_Structure/MapServer/1",
            "where": "DESCRIPTION = 'Building'",
            "fields": "OBJECTID,FEATURECODE,DESCRIPTION,CAPTUREYEAR,CAPTUREACTION,GLOBALID",
            "spatial_from_address": True,
        },
        "currency_note": "The address record identifies a center-of-building placement; the public footprint reports an older capture year and remains a screening geometry, not a survey.",
        "requires_currency_review": True,
    },
    "chicago": {
        "address": "233 S WACKER DR, CHICAGO, IL",
        "address_query": {
            "agency": "Cook County GIS",
            "dataset": "Address Points",
            "url": "https://gis.cookcountyil.gov/traditional/rest/services/addressZipCode/MapServer/0",
            "where": "CMPADDABRV = '233 S WACKER DR' AND geocode_muni = 'CHICAGO'",
            "fields": "OBJECTID,ADDRDELIV,CMPADDABRV,PIN,Post_Comm,State,Post_Code,Long,Lat,last_edited_date",
        },
        "building_query": {
            "agency": "Cook County GIS",
            "dataset": "Building Footprints 2022",
            "url": "https://gis.cookcountyil.gov/traditional/rest/services/buildingFootprint_2022/MapServer/0",
            "where": "1=1",
            "fields": "OBJECTID,Area_SQFT,Year,Height,GlobalID",
            "spatial_from_address": True,
        },
        "parcel_query": {
            "agency": "Cook County GIS and Assessor",
            "dataset": "Current Parcel with Assessment Data",
            "url": "https://gis.cookcountyil.gov/traditional/rest/services/cookVwrDynmc/MapServer/44",
            "where": "Address = '233 S WACKER DR' AND City = 'CHICAGO'",
            "fields": "OBJECTID,Address,City,Zip_Code,PIN14,geom_year,last_edited_date,GlobalID",
        },
        "currency_note": "The parcel is current to geometry year 2025; the building layer is the county's 2022 footprint release.",
        "requires_currency_review": True,
    },
    "tampa": {
        "address": "100 N TAMPA ST, TAMPA, FL",
        "address_query": {
            "agency": "City of Tampa GIS",
            "dataset": "Address Point",
            "url": "https://arcgis.tampagov.net/arcgis/rest/services/OpenData/StreetsandAddresses/MapServer/0",
            "where": "FULLADDR = '100 N Tampa St' AND STATUS = 'Current'",
            "fields": "OBJECTID,STATUS,FULLADDR,UNITID,ADDRNUM,FULLNAME,POINTTYPE,LASTUPDATE,GlobalID",
        },
        "building_query": {
            "agency": "City of Tampa GIS",
            "dataset": "Building Footprint",
            "url": "https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Location/MapServer/0",
            "where": "FULLADDRESS = '100 N Tampa St'",
            "fields": "OBJECTID,STRAP,FOLIO,ADDRNUM,FULLADDRESS,LASTUPDATE,GlobalID",
            "address_field": "FULLADDRESS",
            "expected_address": "100 N Tampa St",
        },
        "currency_note": "Both the address point and addressed building are current City of Tampa operational layers.",
    },
}


def fetch_geojson(spec: dict, point: tuple[float, float] | None = None) -> tuple[dict, str]:
    params = {
        "f": "geojson",
        "where": spec["where"],
        "outFields": spec["fields"],
        "returnGeometry": "true",
        "outSR": "4326",
    }
    if point is not None:
        params.update(
            {
                "geometry": f"{point[0]:.12f},{point[1]:.12f}",
                "geometryType": "esriGeometryPoint",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            }
        )
    response = requests.get(f"{spec['url']}/query", params=params, timeout=45)
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise PropertySupportError(f"{spec['dataset']}: {data['error']}")
    return data, response.url


def candidate(spec: dict, response: dict, record_url: str, role: str) -> dict:
    return {
        "role": role,
        "agency": spec["agency"],
        "dataset": spec["dataset"],
        "service_url": spec["url"],
        "record_url": record_url,
        "retrieved_at": utc_now(),
        "response_sha256": sha256(response),
        "feature_count": len(response.get("features", [])),
        "publication_status": "public_endpoint_capture_terms_not_independently_adjudicated",
        "use_limitations": "Agency GIS screening record; approximate and not a substitute for surveying, engineering, legal, tax, or other professional advice. Review the source's current terms before redistribution or commercial use.",
        "raw_response": response,
    }


def point_coordinates(feature: dict) -> tuple[float, float]:
    geometry = feature.get("geometry")
    if not geometry or geometry.get("type") != "Point":
        raise PropertySupportError("exact address result is not a point")
    lon, lat = geometry["coordinates"][:2]
    return float(lon), float(lat)


def select_support(config: dict, captures: list[dict], census_point: tuple[float, float]) -> tuple[dict | None, list[str]]:
    issues = []
    by_role = {capture["role"]: capture for capture in captures}
    address_capture = by_role.get("address_point")
    parcel_capture = by_role.get("parcel")
    building_capture = by_role.get("building")
    address_point = None

    if address_capture:
        if address_capture["feature_count"] != 1:
            issues.append(f"official address query returned {address_capture['feature_count']} records; expected exactly one")
        else:
            address_point = point_coordinates(address_capture["raw_response"]["features"][0])
    elif not parcel_capture or parcel_capture["feature_count"] != 1:
        issues.append("no publishable exact official address or parcel record confirms the requested property")

    if building_capture:
        if building_capture["feature_count"] != 1:
            issues.append(f"official building query returned {building_capture['feature_count']} records; expected exactly one")
        else:
            feature = building_capture["raw_response"]["features"][0]
            geometry = shape(feature["geometry"])
            if not geometry.is_valid or geometry.is_empty:
                issues.append("official building geometry is empty or invalid")
            if address_point and not geometry.covers(Point(*address_point)):
                issues.append("official address point is not inside the selected official building")
            field = config["building_query"].get("address_field")
            if field and str(feature.get("properties", {}).get(field, "")).upper() != str(config["building_query"]["expected_address"]).upper():
                issues.append("selected building's address field does not exactly match the requested address")
            if not issues:
                _, _, offset = GEOD.inv(census_point[0], census_point[1], *(address_point or geometry.representative_point().coords[0]))
                return {
                    "kind": "official_building_footprint",
                    "confidence_tier": "A" if field else "B",
                    "geometry": feature["geometry"],
                    "source_response_sha256": building_capture["response_sha256"],
                    "address_point": {"longitude": address_point[0], "latitude": address_point[1]} if address_point else None,
                    "census_to_official_anchor_meters": round(offset, 3),
                    "requires_currency_review": bool(config.get("requires_currency_review")),
                }, issues

    if parcel_capture and parcel_capture["feature_count"] == 1:
        feature = parcel_capture["raw_response"]["features"][0]
        geometry = shape(feature["geometry"])
        if geometry.is_valid and not geometry.is_empty:
            if address_point and not geometry.covers(Point(*address_point)):
                issues.append("official address point is not inside the exact-address parcel")
            if not issues:
                anchor = address_point or geometry.representative_point().coords[0]
                _, _, offset = GEOD.inv(census_point[0], census_point[1], *anchor)
                return {
                    "kind": "official_parcel_polygon",
                    "confidence_tier": "C",
                    "geometry": feature["geometry"],
                    "source_response_sha256": parcel_capture["response_sha256"],
                    "address_point": {"longitude": address_point[0], "latitude": address_point[1]} if address_point else None,
                    "census_to_official_anchor_meters": round(offset, 3),
                    "requires_currency_review": bool(config.get("requires_currency_review")),
                }, issues
        else:
            issues.append("official parcel geometry is empty or invalid")

    return None, issues


def collect_one(config: dict, rows: list[dict]) -> dict:
    census_point = (float(rows[0]["longitude"]), float(rows[0]["latitude"]))
    captures = []
    address_point = None
    if config.get("address_query"):
        response, url = fetch_geojson(config["address_query"])
        capture = candidate(config["address_query"], response, url, "address_point")
        captures.append(capture)
        if capture["feature_count"] == 1:
            address_point = point_coordinates(response["features"][0])
    if config.get("building_query"):
        point = address_point if config["building_query"].get("spatial_from_address") else None
        if config["building_query"].get("spatial_from_address") and point is None:
            response = {"type": "FeatureCollection", "features": []}
            url = config["building_query"]["url"] + "/query"
        else:
            response, url = fetch_geojson(config["building_query"], point)
        captures.append(candidate(config["building_query"], response, url, "building"))
    if config.get("parcel_query"):
        response, url = fetch_geojson(config["parcel_query"])
        captures.append(candidate(config["parcel_query"], response, url, "parcel"))

    support, issues = select_support(config, captures, census_point)
    if support and support.get("requires_currency_review"):
        status = "provisional_currency_review_required"
    elif support:
        status = "verified_property_support"
    else:
        status = "blocked_property_identity_or_geometry"
    return {
        "schema_version": "groundtruth_geo_property_support.v1",
        "address": config["address"],
        "case_ids": sorted(row["id"] for row in rows),
        "tasks": sorted({row["task"] for row in rows}),
        "collected_at": utc_now(),
        "status": status,
        "census_center": {"longitude": census_point[0], "latitude": census_point[1]},
        "support": support,
        "issues": issues,
        "currency_note": config["currency_note"],
        "restricted_source_excluded": config.get("restricted_source"),
        "captures": captures,
        "claim_boundary": "Official local screening geometry, not a survey, title opinion, elevation certificate, regulatory determination, or independent professional review.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "groundtruth_geo.jsonl")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    rows = load_rows(args.dataset)
    by_address = {}
    for row in rows:
        by_address.setdefault(row["address"], []).append(row)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = {}
    for key, config in SOURCES.items():
        relevant = by_address.get(config["address"], [])
        if not relevant:
            raise PropertySupportError(f"dataset has no rows for {config['address']}")
        record = collect_one(config, relevant)
        path = args.output_dir / f"{key}.json"
        path.write_bytes(canonical_json(record) + b"\n")
        summary[key] = {"status": record["status"], "issues": record["issues"], "path": str(path)}
    print(json.dumps(summary, indent=2, sort_keys=True))
    # A blocked source is a valid fail-closed collection result, not a program
    # failure. Network, schema, or write failures still raise above.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
