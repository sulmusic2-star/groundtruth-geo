#!/usr/bin/env python3
"""Export a bounded, human-readable run audit for CITYGRAPH."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import refresh_evidence


ROOT = Path(__file__).resolve().parent
TASK_LABELS = {
    "fema_sfha": "FEMA high-risk flood area",
    "historic_district": "National Register historic district",
    "contamination_nearby": "EPA cleanup records within 0.25 mile",
}


def plain_answer(row: dict) -> str:
    answer = row["answer"]
    if row["task"] == "fema_sfha":
        return f"{'Yes' if answer['in_sfha'] else 'No'} — FEMA zone {answer['zone']}"
    if row["task"] == "historic_district":
        if not answer["in_historic_district"]:
            return "No listed National Register district intersects the checked point"
        return "Yes — " + "; ".join(answer["districts"])
    return (
        f"{'Yes' if answer['has_nearby_site'] else 'No'} — {answer['count']} "
        "EPA Superfund/Brownfields record(s) within 0.25 mile"
    )


def build(run_dir: Path, limit: int) -> dict:
    rows = refresh_evidence.load_rows()[:limit]
    predictions_doc = json.loads((run_dir / "predictions.json").read_text())
    audit = json.loads((run_dir / "audit.json").read_text())
    details = {item["item_id"]: item for item in audit["details"]}
    cases = []
    for row in rows:
        evidence = json.loads((ROOT / row["evidence_path"]).read_text())
        prediction = predictions_doc["predictions"].get(row["id"], {})
        result = details[row["id"]]
        records = [
            {
                "source": query["source"],
                "url": query["record_url"],
                "retrieved_at": row["retrieved_at"],
                "returned_records": query["returned_record_count"],
                "qualifying_records": query["qualifying_record_count"],
            }
            for query in evidence["official_queries"]
        ]
        cases.append(
            {
                "id": row["id"],
                "task": row["task"],
                "task_label": TASK_LABELS[row["task"]],
                "address": row["address"],
                "question": row["question"],
                "model_result": "Abstained" if result["abstained"] else ("Accepted" if result["accepted"] else "Failed review"),
                "model_explanation": prediction.get("explanation") or "No explanation was returned.",
                "accepted": result["accepted"],
                "abstained": result["abstained"],
                "official_answer": plain_answer(row),
                "record_checked_at": row["retrieved_at"],
                "official_records": records,
                "review_checks": (
                    {
                        "right_property": "not_tested",
                        "right_official_source": "not_tested",
                        "answer_supported": "no_answer",
                        "citation_opens_the_record": "no_citation",
                        "stopped_when_evidence_missing": "passed",
                        "evidence_current": "not_tested",
                    }
                    if result["abstained"]
                    else {
                        "right_property": "failed" if result["wrong_property"] else "passed",
                        "right_official_source": "failed" if result["wrong_source"] else "passed",
                        "answer_supported": "failed" if result["unsupported_answer"] else "passed",
                        "citation_opens_the_record": "failed" if result["unusable_citation"] else "passed",
                        "stopped_when_evidence_missing": "failed" if result["failure_to_abstain"] else "passed",
                        "evidence_current": "failed" if result["stale_or_undated_evidence"] else "passed",
                    }
                ),
                "review_note": "The model did not guess, but it also did not provide a usable property answer." if result["abstained"] else "; ".join(result["reasons"]),
            }
        )
    accepted = sum(case["accepted"] for case in cases)
    abstained = sum(case["abstained"] for case in cases)
    critical_failures = sum(not case["accepted"] and not case["abstained"] for case in cases)
    return {
        "schema_version": "citygraph_groundtruth_audit.v1",
        "title": "Property answer audit",
        "run_id": predictions_doc["run_id"],
        "condition": "Closed-book model, no property tools or web access",
        "model": predictions_doc["model_requested"],
        "cases_shown": len(cases),
        "summary": {
            "accepted_answers": accepted,
            "safe_abstentions": abstained,
            "critical_failures": critical_failures,
            "answers_still_needed": len(cases) - accepted,
        },
        "claim_boundary": "Observed model run on selected public examples. An abstention avoids an unsupported claim but does not answer the property question. This is not a representative accuracy result.",
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="run directory")
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    payload = build(Path(args.run).resolve(), args.limit)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "passed", "output": str(output), "cases": len(payload["cases"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
