# Replicated review status — August 20, 2026

Status: `multi_method_replicated_not_independent_human`

## Result

- Public cases re-derived: 33 of 33 passed.
- Private cases re-derived: 100 of 100 passed.
- Adversarial mutations detected: 1,064 of 1,064.
- Unique live government responses unchanged: 227 of 227.
- Unresolved stored cases: 0.
- Independent human review: false.

## Evidence

- `replicated_review.py` is a separate implementation and imports neither the
  public evidence generator nor the private holdout builder.
- `proof/replicated-review-public-20260820.json` contains public case-level
  results.
- `proof/replicated-review-private-receipt-20260820.json` contains only the
  private aggregate and commitment; private case-level results remain outside
  the public repository with mode 0600.
- `proof/replicated-review-summary-20260820.json` is the report source.
- `docs/review/validation-receipt.json` records the report validation and
  delivery state.

## Claim boundary

This proves replicated agreement and designed-control behavior on the reviewed
cases. It does not prove independent review, representative statewide or
national accuracy, or a professional determination.
