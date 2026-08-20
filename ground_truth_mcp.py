#!/usr/bin/env python3
"""Ground Truth (static edition) — an MCP server that exposes selected
GroundTruth-Geo rows as a callable agent tool, with no LLM in the lookup path.

This open-source variant returns a row only when an address appears in
``groundtruth_geo.jsonl``. Each v2 row links to a dated evidence receipt and an
exact official record query. Addresses outside the file return a structured
``not in static benchmark`` response.

Run locally:
    python3 ground_truth_mcp.py

Claude Desktop config (drop into ``claude_desktop_config.json``):
    {
      "mcpServers": {
        "ground-truth": {
          "command": "python3",
          "args": ["/absolute/path/to/ground_truth_mcp.py"]
        }
      }
    }

JSON-RPC 2.0 stdio MCP server, minimal-dependency. Works with Claude Desktop
or any MCP client.
"""
import sys
import json
import os
from collections import defaultdict

PROTO = "2024-11-05"
SERVER = {"name": "ground-truth", "version": "0.3.0-evidence"}
HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = os.path.join(HERE, "groundtruth_geo.jsonl")

TASK_LABELS = {
    "fema_sfha": "FEMA Special Flood Hazard Area",
    "historic_district": "National Register historic district",
    "contamination_nearby": "EPA / state-listed contamination sites nearby",
}


def _load_records():
    """Group benchmark items into per-record_id property-truth records."""
    by_addr = defaultdict(list)
    by_rid = {}
    if not os.path.exists(GOLD):
        return by_addr, by_rid
    for line in open(GOLD):
        try:
            it = json.loads(line)
        except json.JSONDecodeError:
            continue
        by_addr[it["address"].upper()].append(it)
        by_rid.setdefault(it["record_id"], it["address"])
    return by_addr, by_rid


_BY_ADDR, _BY_RID = _load_records()


def _truth_for_items(items):
    """Project a list of benchmark items for the same record into the
    canonical Lasting Ground verifier record shape."""
    if not items:
        return {"error": "No records found."}
    head = items[0]
    claims = []
    for it in items:
        claims.append({
            "task": it["task"],
            "claim": TASK_LABELS.get(it["task"], it["task"]),
            "answer": it["answer"],
            "source": it["source"],
            "source_url": it["source_url"],
            "source_date": it["source_date"],
            "retrieved_at": it.get("retrieved_at"),
            "evidence_status": it.get("evidence_status"),
            "evidence_path": it.get("evidence_path"),
            "evidence_sha256": it.get("evidence_sha256"),
            "independent_review": it.get("independent_review", False),
            "deterministic": it.get("deterministic", True),
            "llm_in_answer_path": it.get("llm_in_answer_path", False),
        })
    return {
        "address": head["address"],
        "state": head["state"],
        "coverage": head.get("coverage", "national-point"),
        "record_id": head["record_id"],
        "fingerprint": head["fingerprint"],
        "claims": claims,
        "provenance": {
            "deterministic": True,
            "llm_in_answer_path": False,
            "reproducible": True,
            "static_copy": True,
            "evidence_status": "verified",
            "independent_review": False,
            "source": "GroundTruth-Geo selected static rows",
            "export_origin": "Lasting Ground development output",
        },
    }


def _lookup_by_address(address):
    if not address:
        return {"error": "address is required"}
    key = address.upper().strip()
    items = _BY_ADDR.get(key)
    if not items:
        # Try a forgiving prefix match (street # + street name) for nicer UX
        for k, its in _BY_ADDR.items():
            if k.startswith(key.rstrip(",")) or key.rstrip(",") in k:
                items = its
                break
    if not items:
        return {
            "not_in_static_benchmark": True,
            "address": address,
            "hint": (
                "This static dataset covers 33 selected questions across 7 states. "
                "No result is available here for the requested address."
            ),
            "benchmark_addresses": sorted({a for a in _BY_ADDR})[:12],
        }
    return _truth_for_items(items)


def _lookup_by_record_id(record_id):
    rid = (record_id or "").strip()
    addr = _BY_RID.get(rid)
    if not addr:
        return {"error": f"Unknown record_id: {rid}"}
    return _truth_for_items(_BY_ADDR.get(addr.upper(), []))


TOOLS = [
    {
        "name": "lookup_property_truth",
        "description": (
            "Return a selected static GroundTruth-Geo row when the address is present in "
            "the bundled file. Rows contain structured reference answers, agency labels, "
            "exact official record queries, dated evidence receipts, and structured answers "
            "for three task families. No LLM is in this lookup path. Evidence is dated, not "
            "continuously current, and has not been independently reviewed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Street address, e.g. '72 Easton St, Nantucket, MA'.",
                }
            },
            "required": ["address"],
        },
    },
    {
        "name": "verify_property_record",
        "description": (
            "Read a selected static row again by its record_id (LG-XXXXXXXX) and return "
            "the stored record and fingerprint. Matching output proves stable local retrieval, "
            "not independent review, statewide coverage, or current source status after the "
            "record's retrieval date."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "record_id": {
                    "type": "string",
                    "description": "A Lasting Ground record id, e.g. 'LG-C020DF82'.",
                }
            },
            "required": ["record_id"],
        },
    },
]


def call_tool(name, args):
    args = args or {}
    if name == "lookup_property_truth":
        return _lookup_by_address(args.get("address", ""))
    if name == "verify_property_record":
        return _lookup_by_record_id(args.get("record_id", ""))
    return {"error": f"Unknown tool: {name}"}


def handle(req):
    method = req.get("method")
    rid = req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": PROTO,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER,
            "instructions": (
                "Call lookup_property_truth(address) only to retrieve a selected bundled row. "
                "Treat absent addresses as unsupported. Check retrieved_at and open the exact "
                "official record before relying on a returned row."
            ),
        }}
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        p = req.get("params", {}) or {}
        try:
            out = call_tool(p.get("name"), p.get("arguments"))
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=2)}],
                "isError": bool(isinstance(out, dict) and out.get("error")),
            }}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                "isError": True,
            }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if rid is not None:
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        resp = handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
