# GroundTruth-Geo

[![ci](https://github.com/sulmusic2-star/groundtruth-geo/actions/workflows/ci.yml/badge.svg)](https://github.com/sulmusic2-star/groundtruth-geo/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-2c5b3a)](LICENSE)
[![engine](https://img.shields.io/badge/engine-lastingground.com-34d399)](https://lastingground.com)

**A small, static evaluation set for testing how agents handle address-specific property questions, abstention, and tool use.**

> **Evidence boundary.** This repository contains 33 selected records across
> seven states and three task families. It is an internal demonstration artifact,
> not a representative sample of US properties, an independently audited
> benchmark, or evidence of nationwide product accuracy. No external users,
> customers, revenue, or third-party benchmark adoption are claimed.

The records ask questions such as: *Is this selected property in a FEMA Special
Flood Hazard Area? Is it in a National Register historic district? Are listed
contamination sites nearby?* Each static row contains:

- an agency source label and agency entry-page URL,
- a snapshot label,
- a stable content fingerprint for the exported row, and
- a structured reference answer that the local grader can compare without an
  LLM judge.

The rows were exported from the **Lasting Ground** development system. The
repository ships the selected records, a deterministic grader, and an MCP server
that exposes only those static records. The agency URLs are starting points, not
record-level citations, and labels such as `current` should not be read as proof
that a source was rechecked today.

## What this demonstrates

- **Grounding / factuality evaluation plumbing** — compare a structured model
  answer with a selected reference row.
- **Abstention-aware scoring** — distinguish incorrect answers from
  `NOT_ATTEMPTED`.
- **Tool-use experiments** — expose the same static rows through MCP and test
  closed-book versus tool-assisted behavior.
- **Deterministic grading** — run repeatable comparisons without an LLM judge.

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

## How to run a local model comparison

1. Feed each item's `question` to the model under test; ask for a structured answer keyed on the gold key.
2. Write `{id: answer}` to `predictions.json`.
3. Run the grader:
   ```bash
   python3 grade_groundtruth.py predictions.json
   ```
4. Compare against the always-NO / always-YES / always-ABSTAIN baselines printed by `python3 grade_groundtruth.py` with no args.

The grader follows field-standard factuality literature so the result is credible to AI-lab researchers:

- **CORRECT / INCORRECT / NOT_ATTEMPTED** buckets (SimpleQA, [arXiv:2411.04368](https://arxiv.org/abs/2411.04368))
- **SimpleQA F1** = 2·A·C / (A + C), rewarding abstention
- **Omniscience Index** in [−100, 100] (AA-Omniscience, [arXiv:2511.13029](https://arxiv.org/abs/2511.13029)) — +1 correct, −1 confident-wrong, 0 abstain
- raw accuracy, abstention rate, hallucination (confident-wrong) rate

## v1 exploratory result (33 selected items, 7 states)

| condition | accuracy | SimpleQA-F1 | Omniscience | abstention | hallucination |
|---|---|---|---|---|---|
| Frontier model, **calibrated** (may abstain) | 0% | 0 | 0 | **100%** | 0% |
| Frontier model, **forced-answer** | *refused to guess* | — | — | — | — |
| Static reference answers | **100%** | 100 | +100 | 0% | 0% |

The model rows above are an author-run exploratory check, not an independent
evaluation. The exact predictions are not included in this repository, so those
rows should not be treated as a reproducible third-party model result.

The static reference answers score 100% because they are the gold data used by
the grader. That result validates the grading path; it is not an independent
accuracy measurement of Lasting Ground or evidence that the selected source
rows remain current.

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

- `lookup_property_truth(address)` — returns a selected static record, or a
  structured `not in static benchmark` response.
- `verify_property_record(record_id)` — re-derives the same record by its `record_id`, returning the reproducible fingerprint.

## Roadmap

- Add dated, record-level source links where the publishing agency supports them.
- Publish prompts and prediction files with future model result rows.
- Expand only after documenting sampling, refresh, and independent-review rules.

## Where this came from

This selected record set was generated from internal Lasting Ground development
outputs. [lastingground.com](https://lastingground.com) is a public
demonstration; no paid use, paying customers, or revenue are claimed. This
repository makes the static evaluation records, grader, and MCP wrapper
inspectable while keeping the separate source-acquisition implementation out of
scope.

The architectural idea demonstrated here is narrow: once a reviewed reference
row exists, comparison and retrieval can be deterministic. This artifact does
not replace an official determination or professional judgment.

## License

MIT — see [LICENSE](LICENSE).
