# GroundTruth-Geo

[![ci](https://github.com/sulmusic2-star/groundtruth-geo/actions/workflows/ci.yml/badge.svg)](https://github.com/sulmusic2-star/groundtruth-geo/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-2c5b3a)](LICENSE)

GroundTruth-Geo is a small, inspectable test set for address-specific property
answers. It checks whether a system chose the right property, used the right
official source, supported its answer, supplied a usable record link, used dated
evidence, and stopped when it could not know.

> **What this is not.** The 33 public cases were selected across seven states.
> They are not a representative sample, statewide or national coverage proof,
> an independent audit, or a product accuracy score. The evidence was retrieved
> on August 20, 2026 and is not continuously current. No customer, revenue, or
> third-party adoption is claimed.

## What is included

| Path | Contents |
|---|---|
| `groundtruth_geo.jsonl` | 33 questions: 11 addresses × 3 task families. |
| `evidence/records/` | Dated receipts with the matched property, exact official queries, returned records, hashes, and derivation rules. |
| `refresh_evidence.py` | Refreshes or validates every public evidence receipt. |
| `spatial_evidence/` | Bounded official geometry and layer metadata used for coordinate-sensitivity tests. |
| `collect_spatial_evidence.py` | Captures all sources before writing, or validates bounded geometry, without deciding the answer. |
| `geospatial_review.py` | Third derivation using GEOS/Shapely and PROJ/PyProj plus a 57-point perturbation matrix. |
| `source_history.py` | Creates append-only, hash-chained snapshots and classifies semantic source changes. |
| `history/snapshots/` | Real dated, hash-chained source-history snapshots and semantic replay evidence. |
| `grade_groundtruth.py` | Deterministic answer grader; no LLM judge. |
| `audit_run.py` | Scores wrong property, wrong source, unsupported answer, unusable citation, failure to abstain, and stale evidence. |
| `run_model.py` | Reproducible OpenAI Responses API runner. |
| `runs/openai-gpt-4-1-mini-closed-book-20260820/` | Exact prompt, requests, responses, traces, predictions, hashes, model version, and audit for one observed run. |
| `ground_truth_mcp.py` | Local MCP server exposing only the bundled public records. |
| `proof/private-holdout-receipt.json` | Public-safe receipt for a separate private, permit-free 100-case Massachusetts set; no addresses or gold answers are exposed. |
| `property_support/` | Official local address, building, and parcel receipts for coordinate-sensitive public cases. |
| `property_support_review.py` | Whole-property certain-yes, certain-no, mixed, or blocked review. |
| `challenge/` | Blind challenge builder, strict submission validator, private scorer, commitment, and external attestation. |

## Public questions

The current tasks have deliberately narrow rules:

| Task | Question and rule |
|---|---|
| `fema_sfha` | Does the geocoded point intersect one FEMA NFHL flood-zone polygon, and is `SFHA_TF` true? |
| `historic_district` | Does the point intersect a National Register record whose resource type is `district`? |
| `contamination_nearby` | Is an EPA Superfund or Brownfields point within 0.25 mile? |

These rules do not replace an official determination or professional review.
They make the selected reference answers reproducible.

## Validate the evidence

```bash
python3 refresh_evidence.py --validate
python3 -m pip install -r requirements-spatial.txt
python3 collect_spatial_evidence.py --validate
python3 geospatial_review.py --collection public
python3 source_history.py --validate
python3 -m unittest discover -s tests -v
python3 grade_groundtruth.py
```

Every public item currently has:

- a Census-matched property point;
- an exact official record query;
- the qualifying official records used for the answer;
- a UTC retrieval time and SHA-256 receipt;
- a deterministic derivation rule; and
- `independent_review: false` until a separate reviewer signs it off.

GroundTruth-Geo also ships a separate automated reviewer in
`replicated_review.py`. As of August 20, 2026, that second implementation
re-derived all 133 public and private cases, rejected 1,064 adversarial
mutations, and replayed 227 unique government record URLs without drift. This
is **replicated automated review**, not independent human review or a
representative accuracy estimate. The method and claim boundary are documented
in `docs/replicated-review-protocol.md`.

GroundTruth-Geo also has a third derivation path using GEOS and PROJ rather than
ArcGIS response counts alone. It reconstructs Esri polygons, includes boundary
contact, computes geodesic distance, and moves each coordinate through 57 fixed
positions from 0 to 100 meters. On August 21, 2026, all 33 public and 100 private
center answers agreed with the benchmark. Seven public cases and 23 private
cases changed under at least one tested displacement. Those are sensitivity
flags, not wrong answers or an estimate of geocoder error. See
`docs/spatial-uncertainty-and-history.md`.

The sensitive cases now have a separate whole-property review using official
local address points linked to public building or parcel geometry. It does not
overwrite the point-based benchmark. Five of the seven sensitive cases remain
consistent over the selected property support, one Chicago historic-district
case is mixed across the building footprint, and one Savannah case is blocked
because local official records do not confirm the requested property. See
`docs/property-support-and-blind-challenge.md`.

To refresh the public evidence from the live official services:

```bash
python3 refresh_evidence.py --refresh
```

A refresh can change an answer. Review the diff and rerun the tests before using
the new data.

## Observed closed-book run

The included run used `gpt-4.1-mini-2025-04-14`, the OpenAI Responses API,
temperature 0, structured output, `store: false`, and no tools or web access.
The model abstained on all 33 questions.

| Result | Count |
|---|---:|
| Accepted answers | 0 |
| Safe abstentions | 33 |
| Critical errors | 0 |
| Answers still needed | 33 |

That is a useful safety baseline, not an accuracy victory: the model avoided
unsupported property claims but did not answer any property question. See the
run directory for the exact prompts, predictions, response traces, hashes, and
model identifiers.

To make a new run, set an API key in the environment and use a new output path:

```bash
python3 run_model.py \
  --model gpt-4.1-mini-2025-04-14 \
  --output-dir runs/private/my-run
python3 audit_run.py \
  --run-dir runs/private/my-run
```

The private run directory is ignored by git. Review it before deciding whether
to publish any model output or response identifiers.

## Baseline sanity checks

With the repaired answers, the constant-answer baselines are:

| Baseline | Accuracy | Abstention | Confidently wrong |
|---|---:|---:|---:|
| Always no | 60.6% | 0% | 39.4% |
| Always yes | 39.4% | 0% | 60.6% |
| Always abstain | 0% | 100% | 0% |

A constant answer does not establish useful property reasoning.

## MCP use

The bundled server returns a result only for an address in the public file:

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

- `lookup_property_truth(address)` returns the selected claims and their dated
  evidence metadata.
- `verify_property_record(record_id)` retrieves the same static record again.

Stable retrieval proves the local record is reproducible. It does not prove
independent accuracy or freshness after the recorded retrieval time.

## Private Massachusetts holdout

The private set contains 100 permit-free cases across 39 properties and 22
Massachusetts municipalities. It is stratified, not representative. The public
receipt commits to the private questions, gold answers, and evidence manifest by
hash while keeping all cases and answers private. A third automated geometry
engine passed all 100 center answers and ran 5,700 perturbation samples; the
detailed report remains private. Independent human review is still pending.

The private set is also packaged as a 100-item blind challenge with opaque item
identifiers, a salted gold commitment, an Ed25519 signature, a fixed prediction
schema, submission hashes, and a private scorer. These controls make later
tampering detectable. They do not create evaluator independence: that requires
an unaffiliated participant and, for professional-review claims, a qualified
reviewer who signs the attestation.

## Origin and license

The selected rows came from Lasting Ground development work. The separate source
acquisition system is out of scope here. [lastingground.com](https://lastingground.com)
is a public demonstration; paid use is not claimed.

MIT — see [LICENSE](LICENSE).
