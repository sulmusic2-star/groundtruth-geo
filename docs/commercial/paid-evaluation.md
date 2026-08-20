# Address-specific answer evaluation

**Working offer. Price and schedule are hypotheses until a buyer confirms the scope.**

## The buyer's question

When our product answers a question about a property, can a reviewer trust that
it chose the right place, used the right official record, supported the answer,
linked to usable evidence, used evidence that was current on the stated date,
and stopped when it could not know?

## Fit check before price

The vendor provides five representative questions and the outputs its system
would normally return. Lasting Ground responds in writing with:

- whether the six-check method can evaluate those outputs;
- which official sources would count;
- which questions are out of scope;
- what data the full evaluation would require; and
- a fixed written scope if both sides see a fit.

No price appears in the opening email. Do not turn the fit check into an unpaid
custom audit: it establishes evaluability, not product performance.

## Proposed paid evaluation

### Inputs

- 20–100 address-specific questions selected before the run;
- the vendor's exact answers, citations, timestamps, model or release label,
  and relevant traces it is allowed to share;
- an agreed list of allowed official sources; and
- written authorization for any non-public staging endpoint.

No personal records, customer secrets, resident conversations, permits, or
automated decisions are required.

### Work

1. Freeze the cases, scoring rules, source rules, and system version.
2. Resolve the intended property and preserve the official record used for gold.
3. Score all six checks deterministically where possible.
4. Require a human reviewer for ambiguous property identity or source meaning.
5. Return disputed cases to a written adjudication queue.
6. Rerun an agreed subset after the vendor makes corrections.

### Deliverables

- one machine-readable result per case in JSON and CSV;
- a CITYGRAPH review page with the model answer beside the official evidence;
- a source ledger with retrieval dates and hashes;
- an executive summary of failure patterns, not just an aggregate score;
- a correction log and one bounded retest; and
- a reproducibility receipt naming the tested system version and dataset hash.

### Acceptance rules

An answer is accepted only when all applicable checks pass. An abstention can
avoid a critical error but never counts as an accepted answer. Unknown evidence
cannot be converted to “no.” The report must keep wrong-property errors separate
from wrong-answer errors.

## Commercial hypotheses

These are starting points for a proposal after fit, not posted prices or earned
market value:

| Scope | Working hypothesis |
|---|---:|
| Bounded 20–100 case evaluation | $15,000–$25,000 fixed fee |
| Recurring mid-market release evaluation | $75,000–$150,000 per year |
| OEM or multi-product evaluation program | $200,000–$300,000 per year |

The first paid scope may need to be smaller if the vendor cannot provide enough
cases, traces, or economic value. Do not discount merely for logo value. Reduce
scope, not rigor.

## What the evaluation does not claim

- It is not a certification or regulatory approval.
- It does not prove nationwide accuracy from a Massachusetts holdout.
- It does not evaluate untested product features.
- It does not replace the vendor's own QA, legal review, or professional advice.
- It does not promise zero future errors.

## Conversion condition

Discuss a recurring contract only if the paid evaluation finds repeatable
failure modes or gives the vendor evidence it can use in release, customer,
procurement, or risk review. A one-time report with no repeated decision is not
an annual contract.
