# Replicated review report notes

Audience: technical evaluators.

Required report roles are mapped as follows:

- Title: `GroundTruth-Geo replicated review`
- Technical summary: `The second implementation agreed on all 133 cases`
- Key findings with visual evidence: headline totals, adversarial-detection
  chart and task-level counts
- Scope, data and definitions: `What was reviewed—and what the rates mean`
- Methodology: `A gold-blind reviewer, not a second pass through the generator`
- Limitations and robustness: `What this still cannot prove`
- Recommended next steps: `Make this the release gate`
- Further questions: `The next hard questions`

Visual contract:

- Question: did the semantic reviewer reject every class of deliberately bad
  evidence?
- Takeaway: all eight mutation classes were detected in all 133 cases.
- Family/type: vertical bar plus a compact exact-value key. A horizontal bar
  and native audit tables were tested first but overflowed in portable HTML at
  desktop width.
  The compact A-H chart supplies the visual comparison while adjacent text
  preserves exact names and counts.
- Data: eight categories; 133 attempted mutations per category; detected and
  detection-rate fields retained.
- Surface: native chart and markdown in the validated in-app report artifact.
- Final QA surface: the validated in-app report. Portable HTML was not shipped
  because its browser verifier found horizontal overflow.

The visual shows synthetic control coverage, not an estimate of real-world
error prevalence. The task table is used for exact case counts because that
comparison is an audit lookup rather than a shape question.
