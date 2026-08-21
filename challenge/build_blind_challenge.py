#!/usr/bin/env python3
"""Build an opaque, privately held challenge and a public hash commitment."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import random
import secrets
from collections import Counter
from pathlib import Path

try:
    from .common import canonical_json, digest_file, load_jsonl, utc_now, write_private
except ImportError:
    from common import canonical_json, digest_file, load_jsonl, utc_now, write_private


ROOT = Path(__file__).resolve().parents[1]


PREDICTION_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "GroundTruth-Geo blind challenge submission",
    "type": "object",
    "required": ["schema_version", "challenge_id", "participant", "run", "predictions"],
    "properties": {
        "schema_version": {"const": "groundtruth_geo_blind_submission.v1"},
        "challenge_id": {"type": "string"},
        "participant": {
            "type": "object",
            "required": ["organization", "system_name", "system_version", "submitted_by", "conflicts_disclosed"],
            "properties": {
                "organization": {"type": "string", "minLength": 1},
                "system_name": {"type": "string", "minLength": 1},
                "system_version": {"type": "string", "minLength": 1},
                "submitted_by": {"type": "string", "minLength": 1},
                "conflicts_disclosed": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "run": {
            "type": "object",
            "required": ["started_at", "completed_at", "tools_and_data", "prompt_or_workflow_sha256"],
            "properties": {
                "started_at": {"type": "string"},
                "completed_at": {"type": "string"},
                "tools_and_data": {"type": "array", "items": {"type": "string"}},
                "prompt_or_workflow_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            "additionalProperties": False,
        },
        "predictions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["item_id", "attempted", "answer", "secondary_answer", "requested_address", "matched_address", "longitude", "latitude", "sources", "explanation"],
                "properties": {
                    "item_id": {"type": "string"},
                    "attempted": {"type": "boolean"},
                    "answer": {"type": ["boolean", "null"]},
                    "secondary_answer": {"type": ["string", "null"]},
                    "requested_address": {"type": "string"},
                    "matched_address": {"type": ["string", "null"]},
                    "longitude": {"type": ["number", "null"]},
                    "latitude": {"type": ["number", "null"]},
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["url", "retrieved_at", "record_id", "supports_answer"],
                            "properties": {
                                "url": {"type": "string"},
                                "retrieved_at": {"type": ["string", "null"]},
                                "record_id": {"type": ["string", "null"]},
                                "supports_answer": {"type": "boolean"},
                            },
                            "additionalProperties": False,
                        },
                    },
                    "explanation": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--commitment-output", type=Path, default=ROOT / "challenge" / "commitments" / "current.json")
    args = parser.parse_args()
    questions = load_jsonl(args.questions)
    gold = load_jsonl(args.gold)
    if {item["id"] for item in questions} != {item["id"] for item in gold}:
        raise SystemExit("question and gold item ids differ")
    secret = secrets.token_bytes(32)
    nonce = secrets.token_bytes(32)
    challenge_id = "gtg-blind-" + hashlib.sha256(secret + args.questions.read_bytes()).hexdigest()[:16]
    id_map = {
        item["id"]: "blind-" + hmac.new(secret, item["id"].encode(), hashlib.sha256).hexdigest()[:20]
        for item in questions
    }
    participant_questions = [
        {"item_id": id_map[item["id"]], "task": item["task"], "question": item["question"]}
        for item in questions
    ]
    random.Random(int.from_bytes(secret, "big")).shuffle(participant_questions)
    gold_by_id = {item["id"]: item for item in gold}
    private_items = []
    for original_id, blind_id in id_map.items():
        item = gold_by_id[original_id]
        evidence_path = args.evidence_dir / Path(item["evidence_path"]).name
        if not evidence_path.exists():
            raise SystemExit(f"missing private evidence {evidence_path}")
        private_items.append(
            {
                "item_id": blind_id,
                "original_id": original_id,
                "gold": item,
                "evidence_path": str(evidence_path),
                "evidence_sha256": digest_file(evidence_path),
            }
        )
    private_items.sort(key=lambda item: item["item_id"])
    gold_commitment = hashlib.sha256(nonce + canonical_json(private_items)).hexdigest()
    participant_dir = args.private_output / "participant"
    write_private(participant_dir / "questions.jsonl", participant_questions, jsonl=True)
    write_private(participant_dir / "prediction-schema.json", PREDICTION_SCHEMA)
    protocol = f"""# GroundTruth-Geo blind challenge {challenge_id}

Return one prediction for every item. Abstain when the system cannot identify the exact property and produce current record-level official evidence. Do not infer a negative answer from a failed or incomplete source query. Record every tool and dataset used, preserve the exact system version, and return the completed JSON before any answer key or score is disclosed.

The participant questions contain no gold answers or evidence receipts. Lasting Ground scores only after the submitted file hash is frozen. A participant result is a real external evaluation only when the participant actually ran its system and attested to the recorded workflow. It is not automatically an independent professional review.
"""
    protocol_path = participant_dir / "PROTOCOL.md"
    protocol_path.write_text(protocol)
    protocol_path.chmod(0o600)
    manifest = {
        "schema_version": "groundtruth_geo_blind_manifest.v1",
        "challenge_id": challenge_id,
        "built_at": utc_now(),
        "secret_hex": secret.hex(),
        "gold_commitment_nonce_hex": nonce.hex(),
        "source_questions_sha256": digest_file(args.questions),
        "source_gold_sha256": digest_file(args.gold),
        "participant_questions_sha256": digest_file(participant_dir / "questions.jsonl"),
        "prediction_schema_sha256": digest_file(participant_dir / "prediction-schema.json"),
        "protocol_sha256": digest_file(protocol_path),
        "gold_commitment_sha256": gold_commitment,
        "items": private_items,
    }
    write_private(args.private_output / "manifest.private.json", manifest)
    commitment = {
        "schema_version": "groundtruth_geo_blind_commitment.v1",
        "challenge_id": challenge_id,
        "built_at": manifest["built_at"],
        "item_count": len(private_items),
        "task_counts": dict(sorted(Counter(item["gold"]["task"] for item in private_items).items())),
        "participant_questions_sha256": manifest["participant_questions_sha256"],
        "prediction_schema_sha256": manifest["prediction_schema_sha256"],
        "protocol_sha256": manifest["protocol_sha256"],
        "gold_commitment_sha256": gold_commitment,
        "commitment_status": "signed_commitment_publication_proven_by_repository_history",
        "claim_boundary": "This commitment proves later file consistency after publication; by itself it does not prove evaluator independence or professional review.",
    }
    args.commitment_output.parent.mkdir(parents=True, exist_ok=True)
    args.commitment_output.write_bytes(canonical_json(commitment) + b"\n")
    print(json.dumps({"challenge_id": challenge_id, "items": len(private_items), "private_output": str(args.private_output), "commitment_output": str(args.commitment_output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
