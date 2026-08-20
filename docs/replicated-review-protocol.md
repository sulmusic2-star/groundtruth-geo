# Replicated review protocol

## What this review is

GroundTruth-Geo now has a second evidence reviewer that does not import the
public evidence generator or the private holdout builder. For every case it:

1. verifies the evidence commitment and every stored response digest;
2. reconstructs the matched property from the raw Census or MassGIS response;
3. checks the exact government host, layer, query point, spatial relation,
   radius and units;
4. derives the flood, historic-district or cleanup answer from raw response
   features while the stored answer is hidden;
5. reveals the stored answer only after derivation and records disagreement as
   unresolved;
6. reopens every unique government record URL and compares the current response
   with the stored response; and
7. runs eight re-hashed adversarial mutations against every case.

The implementation is [replicated_review.py](../replicated_review.py). It does
not use `refresh_evidence.py` as a library and does not trust the receipt's
`gold_answer`, `qualifying_records`, counts, coordinates or source URL.

The public set can be reviewed from the repository root. A private review
requires an explicit `--root` path so no private workspace location is embedded
in the public code.

## Synthetic review roles

The reviewer separates the work a careful evidence reviewer performs into
seven gates:

- **Case contract:** the item, task, status and evidence commitment agree.
- **Integrity:** response and receipt digests agree with their commitments.
- **Property identity:** the raw address response identifies the same property
  and coordinates used by every downstream query.
- **Source authority:** the URL is HTTPS, uses the allowed government host and
  exact program layer, and preserves the required spatial parameters.
- **Domain derivation:** the answer is recalculated from raw returned features,
  including record filtering, distance calculation and deduplication.
- **Answer adjudication:** an unavailable or ambiguous response remains
  unresolved; it cannot become “no.”
- **Freshness:** evidence older than the configured limit is rejected.

This structure can exceed one manual review in consistency, repeatability,
tamper detection and coverage. It cannot supply human independence,
professional accountability or legal judgment.

## Adversarial acceptance test

Each real case is copied in memory and attacked eight ways. The mutated receipt
is re-hashed after most attacks so a simple outer checksum is not enough to
pass. The reviewer must reject:

- a non-government source domain;
- a government query aimed at the wrong point;
- stale evidence;
- a property coordinate inconsistent with the raw property record;
- a false returned-record count;
- false qualifying records;
- a changed stored answer; and
- a source error rewritten as a negative answer.

The acceptance rule is 100% detection. A missed mutation fails the replicated
review release.

## Current result

As of August 20, 2026:

- 133 of 133 stored cases were independently re-derived by the second
  implementation with no disagreements;
- all 1,064 adversarial mutations were detected; and
- all 227 unique live government responses matched the stored responses.

The public evidence is in `proof/replicated-review-public-20260820.json`. The
private case-level review remains in the private holdout workspace; only its
aggregate receipt and commitment are public.

## Claim boundary

Use this wording:

> GroundTruth-Geo passed a gold-blind, second-implementation review of 133
> stored cases, rejected 1,064 adversarial mutations and replayed 227 live
> government records without drift. This is replicated automated review, not
> independent human review or representative field-accuracy proof.

Do not set `independent_review: true`. An external reviewer remains useful for
procurement credibility, domain accountability and discovering shared
assumptions that both internal implementations may contain.
