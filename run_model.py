#!/usr/bin/env python3
"""Run the public benchmark through the OpenAI Responses API and save the trace."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
import time
from pathlib import Path

import openai
from openai import OpenAI

import refresh_evidence


ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
DEFAULT_MODEL = "gpt-4.1-mini-2025-04-14"

SYSTEM_PROMPT = """You are being evaluated on address-specific official property facts.
This is a closed-book run: you have no browser, property database or government-record tool.
Do not guess and do not rely on general memory. A general agency homepage is not a usable citation.
Attempt an answer only when you can identify the property, give a record-level official URL,
and state when that record was retrieved. Otherwise set attempted to false and answer to null.
Return only the required structured fields."""

ITEM_TEMPLATE = """Item id: {id}
Question: {question}
Requested address: {address}

Evaluate only this item. If official, address-specific evidence is unavailable in this run, abstain."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "attempted": {"type": "boolean"},
        "answer": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
        "secondary_answer": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "requested_address": {"type": "string"},
        "matched_address": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "longitude": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "latitude": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "retrieved_at": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "record_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "supports_answer": {"type": "boolean"},
                },
                "required": ["url", "retrieved_at", "record_id", "supports_answer"],
                "additionalProperties": False,
            },
        },
        "explanation": {"type": "string"},
    },
    "required": [
        "attempted",
        "answer",
        "secondary_answer",
        "requested_address",
        "matched_address",
        "longitude",
        "latitude",
        "sources",
        "explanation",
    ],
    "additionalProperties": False,
}


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def request_for(row: dict, model: str) -> dict:
    return {
        "model": model,
        "store": False,
        "temperature": 0,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": ITEM_TEMPLATE.format(id=row["id"], question=row["question"], address=row["address"]),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "property_evidence_answer",
                "strict": True,
                "schema": OUTPUT_SCHEMA,
            }
        },
    }


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL, help="dated OpenAI model snapshot")
    parser.add_argument("--run-id", help="directory name under runs/")
    parser.add_argument("--limit", type=int, help="run only the first N items for a smoke test")
    args = parser.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is not set")
    evidence_validation = refresh_evidence.validate()
    rows = refresh_evidence.load_rows()
    if args.limit:
        rows = rows[: args.limit]
    run_id = args.run_id or f"openai-{args.model}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = RUNS / run_id
    if run_dir.exists():
        parser.error(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text(
        "SYSTEM\n" + SYSTEM_PROMPT + "\n\nITEM TEMPLATE\n" + ITEM_TEMPLATE + "\n"
    )
    requests_path = run_dir / "requests.jsonl"
    responses_path = run_dir / "responses.jsonl"
    traces_path = run_dir / "traces.jsonl"
    predictions = {}
    actual_models = set()
    response_ids = []
    started_at = utc_now()
    client = OpenAI()
    with requests_path.open("w") as requests_file, responses_path.open("w") as responses_file, traces_path.open("w") as traces_file:
        for index, row in enumerate(rows, start=1):
            request_body = request_for(row, args.model)
            request_record = {"item_id": row["id"], "request": request_body}
            requests_file.write(json.dumps(request_record, ensure_ascii=False) + "\n")
            requests_file.flush()
            began = time.monotonic()
            response = client.responses.create(**request_body)
            latency_ms = round((time.monotonic() - began) * 1000)
            response_dict = response.to_dict()
            responses_file.write(json.dumps({"item_id": row["id"], "response": response_dict}, ensure_ascii=False) + "\n")
            responses_file.flush()
            parsed = json.loads(response.output_text)
            predictions[row["id"]] = parsed
            actual_models.add(response.model)
            response_ids.append(response.id)
            trace = {
                "sequence": index,
                "item_id": row["id"],
                "request_sha256": refresh_evidence.sha256(request_body),
                "response_id": response.id,
                "response_model": response.model,
                "status": response.status,
                "latency_ms": latency_ms,
                "usage": response_dict.get("usage"),
                "parsed": True,
            }
            traces_file.write(json.dumps(trace, ensure_ascii=False) + "\n")
            traces_file.flush()
            print(f"[{index:02d}/{len(rows):02d}] {row['id']} {response.status} {latency_ms}ms")
    predictions_document = {
        "schema_version": "2.0",
        "run_id": run_id,
        "condition": "closed_book_no_tools",
        "model_requested": args.model,
        "models_returned": sorted(actual_models),
        "dataset_sha256": digest_file(refresh_evidence.DATASET),
        "predictions": predictions,
    }
    write_json(run_dir / "predictions.json", predictions_document)
    files = ["prompt.txt", "requests.jsonl", "responses.jsonl", "traces.jsonl", "predictions.json"]
    manifest = {
        "schema_version": "2.0",
        "run_id": run_id,
        "condition": "closed_book_no_tools",
        "started_at": started_at,
        "completed_at": utc_now(),
        "dataset": "groundtruth_geo.jsonl",
        "dataset_sha256": digest_file(refresh_evidence.DATASET),
        "dataset_items": len(rows),
        "public_evidence_validation": evidence_validation,
        "git_commit_before_run": git_commit(),
        "model_requested": args.model,
        "models_returned": sorted(actual_models),
        "response_ids": response_ids,
        "api": "OpenAI Responses API",
        "api_storage_requested": False,
        "tools": [],
        "temperature": 0,
        "python": platform.python_version(),
        "openai_python": openai.__version__,
        "runner": "run_model.py",
        "file_sha256": {name: digest_file(run_dir / name) for name in files},
        "reproducibility_note": "The dated model snapshot and exact requests are preserved. Model sampling may still produce different text on a later rerun.",
    }
    write_json(run_dir / "manifest.json", manifest)
    print(json.dumps({"status": "completed", "run_dir": str(run_dir), "items": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
