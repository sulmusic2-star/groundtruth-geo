# Baseline results

This document records the v1 constant-answer outputs from the local grader and
an author-run exploratory model check.

> **Interpretation boundary.** The 33 records are selected development outputs,
> not a representative or independently audited sample. The model prompt and
> prediction file are not included, so the model rows below are not fully
> reproducible. The static reference rows score 100% by construction and do not
> establish product accuracy.

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

**The author-run calibrated result:** Claude abstained on all 33 selected
questions in this run. No claim is made about other prompts, models, properties,
or runs.

**The author-run forced-answer result:** the model declined to provide the
requested booleans. Because the prompt and response artifact are not published,
this row should be treated as a descriptive note rather than a benchmark score.

## Static reference rows

The selected Lasting Ground development outputs are the gold rows used by the
grader. They are, by construction, 100% / +100 / 0% hallucination when compared
with themselves.

| condition | accuracy | SimpleQA F1 | Omniscience | abstention | hallucination |
|---|---|---|---|---|---|
| Static reference answers | **100%** | 100 | +100 | 0% | 0% |

This validates the local comparison path. It is not an independent accuracy,
freshness, or coverage result for Lasting Ground.

## How to run your own local model comparison

1. Loop over `groundtruth_geo.jsonl`. For each item, send the `question` to your model.
2. Ask for a JSON answer keyed on the gold key (see `predictions-sample.json` for the exact shape, including the calibrated `{"NOT_ATTEMPTED": true}` form).
3. Write `{item_id: model_answer}` to `predictions.json`.
4. Run `python3 grade_groundtruth.py predictions.json` — it prints per-task and overall metrics.
5. Preserve the model name, prompt, predictions, and condition with any result
   you report so another person can reproduce the comparison.

The grader does not call a model. It compares structured booleans against the
selected static records.

## Why these metrics

- **CORRECT / INCORRECT / NOT_ATTEMPTED buckets:** [SimpleQA (Wei et al., 2024)](https://arxiv.org/abs/2411.04368) — the standard short-form factuality bucketing.
- **SimpleQA F1 = 2·A·C / (A + C):** rewards abstention. C is recall-like (correct/N); A is precision-like (correct/(correct+incorrect)). Guessing wrong hurts; saying "I don't know" doesn't inflate the score.
- **Omniscience Index in [−100, +100]:** [AA-Omniscience (2025)](https://arxiv.org/abs/2511.13029). +1 correct, −1 confident-wrong, 0 abstain. 0 means "right as often as wrong" — a constant answer lands here.
- **abstention rate** + **hallucination (confident-wrong) rate:** the most honest, plain-English summaries of model behavior.
