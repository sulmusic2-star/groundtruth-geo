# Baseline results

The benchmark is designed to be ungameable by a constant answer. This document records the v1 baseline results — what the grader actually outputs when run against the constant baselines and against a closed-book frontier model.

## Always-NO / always-YES / always-ABSTAIN baselines (deterministic, run by `python3 grade_groundtruth.py`)

| condition | n | accuracy | SimpleQA F1 | Omniscience | abstention | hallucination |
|---|---|---|---|---|---|---|
| always-NO   | 33 | 54.5% | 54.5 | +9  | 0% | 45.5% |
| always-YES  | 33 | 45.5% | 45.5 | −9  | 0% | 54.5% |
| always-ABSTAIN | 33 | 0% | 0 | 0 | 100% | 0% |

A constant answer lands near zero on the Omniscience Index because the benchmark is a real yes/no mix (slightly NO-skewed on the v1 sample). The point of `always-ABSTAIN` is to make explicit that the grader rewards calibrated abstention with 0 — not credit, but no penalty either.

## Closed-book frontier model — Claude (Anthropic)

Methodology, 33 items, 7 states (MA, FL, GA, CA, TX, DC, IL):

1. The grader's `question` text is sent to the model with no tools and no web access.
2. The model is asked to return a structured object whose key matches the gold key for the task (`in_sfha` / `in_historic_district` / `has_nearby_site`).
3. Two prompt conditions were evaluated:
   - **Calibrated:** the model may abstain by returning `{"NOT_ATTEMPTED": true}` if it doesn't know.
   - **Forced-answer:** the model is instructed to commit to a boolean even under uncertainty.
4. Predictions are written to `predictions.json` and graded with `python3 grade_groundtruth.py predictions.json`.

| condition | accuracy | SimpleQA F1 | Omniscience | abstention | hallucination |
|---|---|---|---|---|---|
| Calibrated (may abstain) | **0%** | 0 | 0 | **100%** | 0% |
| Forced-answer | refused to guess | — | — | — | — |

**The calibrated finding:** Claude abstains on **100%** of these parcel-precise factual questions. It correctly recognizes it cannot answer them from parametric memory: FEMA flood-zone determinations and National Register district boundaries are not in the training corpus at parcel precision.

**The forced-answer finding:** instructed into the *forced-answer* condition, Claude refused to hallucinate, stating that emitting confident booleans about real parcels "is exactly the hallucinated, unverifiable output that causes real harm in this domain." This is itself the on-thesis result for an Anthropic-built model — the model's own calibration is the evidence that a parametric LLM is not the right surface for these answers.

## The reference oracle — Lasting Ground (tool-backed)

The Lasting Ground engine (private, live at [lastingground.com](https://lastingground.com)) is the source of the gold answers — it is, by construction, 100% / +100 / 0% hallucination on this benchmark because the benchmark was *generated* from its outputs with deterministic provenance.

| condition | accuracy | SimpleQA F1 | Omniscience | abstention | hallucination |
|---|---|---|---|---|---|
| Lasting Ground (tool-backed) | **100%** | 100 | +100 | 0% | 0% |

The closed-book → tool gap is the artifact. The parametric knowledge is absent (the model knows it); the cited engine supplies it.

## How to publish your own model score

1. Loop over `groundtruth_geo.jsonl`. For each item, send the `question` to your model.
2. Ask for a JSON answer keyed on the gold key (see `predictions-sample.json` for the exact shape, including the calibrated `{"NOT_ATTEMPTED": true}` form).
3. Write `{item_id: model_answer}` to `predictions.json`.
4. Run `python3 grade_groundtruth.py predictions.json` — it prints per-task and overall metrics.
5. Open a PR adding your result row to this table (include model name, prompt, and condition).

The grader does not call a model. It compares structured booleans against cited government records. No reward-hacking surface.

## Why these metrics

- **CORRECT / INCORRECT / NOT_ATTEMPTED buckets:** [SimpleQA (Wei et al., 2024)](https://arxiv.org/abs/2411.04368) — the standard short-form factuality bucketing.
- **SimpleQA F1 = 2·A·C / (A + C):** rewards abstention. C is recall-like (correct/N); A is precision-like (correct/(correct+incorrect)). Guessing wrong hurts; saying "I don't know" doesn't inflate the score.
- **Omniscience Index in [−100, +100]:** [AA-Omniscience (2025)](https://arxiv.org/abs/2511.13029). +1 correct, −1 confident-wrong, 0 abstain. 0 means "right as often as wrong" — a constant answer lands here.
- **abstention rate** + **hallucination (confident-wrong) rate:** the most honest, plain-English summaries of model behavior.
