# Reproducible run contract

A reported model result must point to a run directory that contains all of the
following files:

- `manifest.json` — dataset digest, git commit, requested and returned model
  identifiers, software versions, timestamps, request count and file digests;
- `prompt.txt` — the exact system instruction and item prompt template;
- `requests.jsonl` — the complete API request for every item, excluding the API
  key;
- `responses.jsonl` — the complete API response returned for every item;
- `traces.jsonl` — item id, request digest, response id, status, latency, token
  use and parse result;
- `predictions.json` — the parsed answers used by the grader;
- `audit.json` and `audit.md` — the deterministic six-dimension audit.

The runner uses a dated model snapshot. That makes the run inspectable and
rerunnable; it does not promise bit-for-bit identical model text. The API key is
read from the environment and is never written to a run artifact.

## Run conditions

The first published run is intentionally closed-book: no web search, no
GroundTruth-Geo records and no Lasting Ground tools are given to the model. The
model is explicitly allowed to abstain. This measures whether it guesses when
it lacks address-specific official evidence; it does not measure a tool-assisted
property system.

Future vendor evaluations must document every tool, source and retrieval trace
made available to the evaluated system.
