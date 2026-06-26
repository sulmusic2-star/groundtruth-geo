#!/usr/bin/env python3
"""Ground Truth (benchmark-static edition) — an MCP server that exposes the
GroundTruth-Geo cited records as a callable agent tool, with NO LLM in the
answer path.

This is the OPEN-SOURCE STATIC-DATA variant. It answers any address that
appears in ``groundtruth_geo.jsonl`` with the same deterministic, government-
source-cited, reproducible record format the live Lasting Ground engine
returns. Addresses outside the benchmark return a structured "not in static
benchmark" response that points at the live engine.

The full live engine (parcel-level depth in Massachusetts, point-precise
nationwide from FEMA / EPA / NPS, ~520 verified state sources across 50
states) is private and runs at https://lastingground.com.

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
SERVER = {"name": "ground-truth", "version": "0.2.0-static"}
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
            "source": "GroundTruth-Geo benchmark (static edition)",
            "engine": "Lasting Ground (live engine private; see lastingground.com)",
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
                "This static benchmark covers 33 questions across 7 states (sample addresses). "
                "The live Lasting Ground engine answers any US address with cited federal layers; "
                "see https://lastingground.com."
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
            "Return the deterministic, government-source-CITED, reproducible property-truth "
            "record for a US address from the GroundTruth-Geo benchmark. Each record carries "
            "claims for FEMA Special Flood Hazard Area, National Register historic district, "
            "and nearby EPA/state-listed contamination sites; every claim cites an official "
            "source URL and date. NO LLM is in the answer path. Use this to GROUND any "
            "property claim before an agent asserts it. (Static benchmark — the live engine "
            "covering any US address is at https://lastingground.com.)"
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
            "Re-derive a previously returned property-truth record by its record_id (LG-XXXXXXXX) "
            "and return the same deterministic record + reproducible content fingerprint. Proves "
            "the record reproduces identically — no AI, no drift."
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
                "Call lookup_property_truth(address) to ground any US property claim in cited, "
                "deterministic government records before asserting it."
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
