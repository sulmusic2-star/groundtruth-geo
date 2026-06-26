# GroundTruth-Geo

[![ci](https://github.com/sulmusic2-star/groundtruth-geo/actions/workflows/ci.yml/badge.svg)](https://github.com/sulmusic2-star/groundtruth-geo/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-2c5b3a)](LICENSE)
[![engine](https://img.shields.io/badge/engine-lastingground.com-34d399)](https://lastingground.com)

**A deterministic, government-cited, reproducible benchmark of parcel-precise US property facts — on the exact questions frontier models fail.**

Frontier LLMs are demonstrably weak at real-world geography: on published benchmarks (GPSBench, MapEval) **no model exceeds ~67%**, city-level localization sits at **1–23%**, and parcel/polygon-geometry tasks fall **under 25%**. Yet these are the facts that decide ~$30T of US property: *Is the building in a FEMA flood zone? Is the parcel in a National Register historic district? Are there EPA-listed contamination sites nearby?*

GroundTruth-Geo asks exactly those questions, where every answer is a **deterministic government record** with:

- an **official source URL** (FEMA NFHL, NPS NRHP, EPA FRS, MassGIS, MassDEP, …),
- a **source date**,
- a **reproducible content fingerprint** (re-run → identical answer), and
- **no LLM in the answer path** — the ground truth is external and dated, so the verifier is **ungameable** (you cannot reward-hack a FEMA panel).

The benchmark is produced by the **Lasting Ground** engine, which answers any US address from national federal layers (parcel-level depth in Massachusetts today, point-precise nationwide from FEMA / EPA / NPS). The live engine is private; this repo ships the **benchmark records, the deterministic grader, and an MCP server** that exposes those records to any agent.

## Why a frontier lab cares

- **Grounding / factuality evals** — a clean, authoritative, callable real-world fact source. The MCP tool ships alongside this repo so a model can be evaluated *with* the verifier and *against* the verifier on the same questions.
- **RL reward verifier** — deterministic grading against cited records. Labs are spending >$1B/yr on RL environments and the live research problem is *verifier quality*: model-based verifiers get hacked, rule-based ones are brittle. This isn't either — it's external government ground truth.
- **The narrative** — "auditable, not algorithmic" — the literal antidote to the December 2025 First Street / Zillow black-box-score collapse.

## Files

| File | Purpose |
|---|---|
| `groundtruth_geo.jsonl` | The benchmark. One item per line (33 items, 7 states). |
| `grade_groundtruth.py` | The deterministic grader — field-standard factuality metrics, no LLM judge. |
| `ground_truth_mcp.py` | An MCP server (JSON-RPC stdio) exposing the records as `lookup_property_truth(address)` and `verify_property_record(record_id)` tools. |

Each benchmark item looks like:

```json
{
  "id": "gtg-be9c68f9073f",
  "task": "fema_sfha",
  "question": "Is the property at \"72 Easton St, Nantucket, MA\" in a FEMA Special Flood Hazard Area?...",
  "answer": {"in_sfha": true, "zone": "AE"},
  "source": "FEMA National Flood Hazard Layer",
  "source_url": "https://msc.fema.gov/portal/home",
  "source_date": "FEMA NFHL (current)",
  "address": "72 EASTON ST, NANTUCKET, MA, 02554",
  "state": "MA",
  "record_id": "LG-C020DF82",
  "fingerprint": "ccd05bcec753",
  "deterministic": true,
  "llm_in_answer_path": false,
  "reproducible": true
}
```

## Tasks (v1)

| task | question | gold key |
|---|---|---|
| `fema_sfha` | building/parcel in a FEMA Special Flood Hazard Area? | `in_sfha` (+ `zone`) |
| `historic_district` | parcel within a National Register historic district? | `in_historic_district` (+ `district`) |
| `contamination_nearby` | EPA/state-listed contamination sites nearby? | `has_nearby_site` (+ `count`) |

## How to publish a model score

1. Feed each item's `question` to the model under test; ask for a structured answer keyed on the gold key.
2. Write `{id: answer}` to `predictions.json`.
3. Run the grader:
   ```bash
   python3 grade_groundtruth.py predictions.json
   ```
4. Compare against the always-NO / always-YES / always-ABSTAIN baselines printed by `python3 grade_groundtruth.py` with no args. A constant answer must not win — that's the point of real ground truth.

The grader follows field-standard factuality literature so the result is credible to AI-lab researchers:

- **CORRECT / INCORRECT / NOT_ATTEMPTED** buckets (SimpleQA, [arXiv:2411.04368](https://arxiv.org/abs/2411.04368))
- **SimpleQA F1** = 2·A·C / (A + C), rewarding abstention
- **Omniscience Index** in [−100, 100] (AA-Omniscience, [arXiv:2511.13029](https://arxiv.org/abs/2511.13029)) — +1 correct, −1 confident-wrong, 0 abstain
- raw accuracy, abstention rate, hallucination (confident-wrong) rate

## v1 result — closed-book frontier model vs the cited engine (33 items, 7 states)

| condition | accuracy | SimpleQA-F1 | Omniscience | abstention | hallucination |
|---|---|---|---|---|---|
| Frontier model, **calibrated** (may abstain) | 0% | 0 | 0 | **100%** | 0% |
| Frontier model, **forced-answer** | *refused to guess* | — | — | — | — |
| **Lasting Ground engine** (tool-backed, the gold) | **100%** | 100 | +100 | 0% | 0% |

A calibrated frontier model (Claude) **abstains on 100%** of these parcel-precise flood / historic-district / contamination questions — it correctly recognizes it cannot answer them from parametric memory. Instructed into the *forced-answer* condition, it **refused to hallucinate**, stating that emitting confident booleans about real parcels "is exactly the hallucinated, unverifiable output that causes real harm in this domain."

The Lasting Ground engine answers **every** item deterministically, each cited to FEMA / NPS / EPA with a source date and a reproducible fingerprint. The closed-book → tool gap **is** the product: the parametric knowledge is absent (the model knows it), and the cited engine supplies it. This is the MapEval-style closed-book-vs-tool split, and it is especially on-thesis for Anthropic — Claude's own calibration is the evidence.

Baselines for sanity: always-NO F1 54.5 / Omni +9, always-YES F1 45.5 / Omni −9, always-ABSTAIN Omni 0 — a constant answer cannot win.

## Use it as an MCP tool

`ground_truth_mcp.py` is a minimal JSON-RPC stdio MCP server that exposes the benchmark records as callable agent tools. It works with Claude Desktop or any MCP client.

Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ground-truth": {
      "command": "python3",
      "args": ["/absolute/path/to/groundtruth-geo/ground_truth_mcp.py"]
    }
  }
}
```

The server exposes two tools:

- `lookup_property_truth(address)` — returns the cited record for an address in the benchmark, or a structured "not in static benchmark" response pointing at the live engine.
- `verify_property_record(record_id)` — re-derives the same record by its `record_id`, returning the reproducible fingerprint.

## Roadmap

- Scale addresses to thousands across all 50 states (the nationwide engine already supports it).
- Add national wetlands (USFWS NWI) + wildfire (USFS WHP) tasks once clean endpoints are wired.
- Parcel-level "building-vs-lot flood" task nationwide once national parcels are licensed — the hardest task for a model, and the moat.

## Where this came from

This benchmark is generated by [Lasting Ground](https://lastingground.com) — a live, paid US property-records answer engine that resolves any US address into source-cited public-records answers from a dozen-plus official government systems, with the source name and date stamped on every line. The live engine is private; this benchmark, the grader, and the MCP server are the evaluation surface, open-sourced.

The architectural decision the benchmark exists to demonstrate: **no LLM is in the answer hot path.** A compliance-adjacent answer (flood zone, contamination, historic-district status) has to be reproducible and traceable to an official source every time. Models build and operate the system; deterministic code answers the customer.

## License

MIT — see [LICENSE](LICENSE).
