#!/usr/bin/env python3
"""Grade model predictions against selected static GroundTruth-Geo reference rows
without an LLM judge. The output includes:

  • CORRECT / INCORRECT / NOT_ATTEMPTED buckets (SimpleQA, arXiv 2411.04368).
  • SimpleQA F1 = 2*A*C/(A+C),  C = correct/N (recall-like),  A = correct/(correct+incorrect) (precision-like).
    Rewards abstention: guessing wrong hurts; saying "I don't know" doesn't inflate the score.
  • Omniscience Index = 100*(correct - incorrect)/N  in [-100, 100]  (AA-Omniscience, arXiv 2511.13029):
    +1 correct, -1 confident-wrong, 0 abstention. 0 == "right as often as wrong."
  • raw accuracy, abstention rate, hallucination (confident-wrong) rate.

Usage:
  python3 grade_groundtruth.py predictions.json     # {item_id: {<gold_key>: value}}  or  {"NOT_ATTEMPTED": true}
  python3 grade_groundtruth.py                       # scores always-NO / always-YES / always-ABSTAIN baselines
A constant answer should not dominate this selected yes/no mix.
"""
import sys, os, json
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = os.path.join(HERE, "groundtruth_geo.jsonl")
KEY = {"fema_sfha": "in_sfha", "historic_district": "in_historic_district", "contamination_nearby": "has_nearby_site"}

def load_gold():
    return [json.loads(l) for l in open(GOLD)] if os.path.exists(GOLD) else []

def _abstained(pred):
    if pred is None: return True
    if isinstance(pred, dict):
        if pred.get("NOT_ATTEMPTED") or pred.get("abstain"): return True
        v = pred.get("answer")
        if isinstance(v, str) and v.strip().upper() in ("NOT_ATTEMPTED", "IDK", "I DON'T KNOW", "UNKNOWN"): return True
    return False

def grade_item(it, pred):
    """-> 'CORRECT' | 'INCORRECT' | 'NOT_ATTEMPTED'."""
    k = KEY.get(it["task"])
    if not k: return None
    if _abstained(pred): return "NOT_ATTEMPTED"
    got = pred.get(k) if isinstance(pred, dict) else pred
    return "CORRECT" if bool(got) == bool(it["answer"].get(k)) else "INCORRECT"

def metrics(counts):
    c, i, n = counts["CORRECT"], counts["INCORRECT"], counts["NOT_ATTEMPTED"]
    N = max(1, c + i + n)
    C = c / N
    A = c / max(1, c + i)
    f1 = (2 * A * C / (A + C)) if (A + C) else 0.0
    return dict(n=c+i+n, correct=c, incorrect=i, abstained=n,
                accuracy=100*C, attempted_accuracy=100*A, f1=100*f1,
                omniscience=100*(c - i)/N, abstention_rate=100*n/N, hallucination_rate=100*i/N)

def report(name, gold, predict):
    by_task = defaultdict(lambda: defaultdict(int)); overall = defaultdict(int)
    for it in gold:
        g = grade_item(it, predict(it))
        if g is None: continue
        by_task[it["task"]][g] += 1; overall[g] += 1
    print(f"\n=========== {name} ===========")
    print(f"  {'task':22} {'n':>3} {'acc%':>6} {'F1':>6} {'Omni':>6} {'abst%':>6} {'halluc%':>7}")
    for task in sorted(by_task):
        m = metrics(by_task[task])
        print(f"  {task:22} {m['n']:>3} {m['accuracy']:>6.1f} {m['f1']:>6.1f} {m['omniscience']:>6.0f} {m['abstention_rate']:>6.1f} {m['hallucination_rate']:>7.1f}")
    m = metrics(overall)
    print(f"  {'OVERALL':22} {m['n']:>3} {m['accuracy']:>6.1f} {m['f1']:>6.1f} {m['omniscience']:>6.0f} {m['abstention_rate']:>6.1f} {m['hallucination_rate']:>7.1f}")
    return m

def main():
    gold = load_gold()
    if not gold:
        print("No benchmark found — run gen_groundtruth_benchmark.py first."); return
    print(f"GroundTruth-Geo: {len(gold)} selected items, {len({g['state'] for g in gold})} states. "
          "Static reference rows; no LLM judge.")
    print("Boundary: not representative, independently audited, or proof of current source status.")
    print("Metrics: accuracy, SimpleQA-F1 (rewards abstention), Omniscience Index [-100,100], abstention & hallucination rates.")
    if len(sys.argv) > 1:
        preds = json.load(open(sys.argv[1]))
        report(f"model: {os.path.basename(sys.argv[1])}", gold, lambda it: preds.get(it["id"]))
    else:
        report("baseline: always-NO", gold, lambda it: {KEY[it["task"]]: False})
        report("baseline: always-YES", gold, lambda it: {KEY[it["task"]]: True})
        report("baseline: always-ABSTAIN", gold, lambda it: {"NOT_ATTEMPTED": True})
        print("\nOmniscience Index: +1 correct / -1 confident-wrong / 0 abstain. A constant answer lands near 0 — that's the point.")
        print("Pass structured answers in predictions.json to run a local comparison.")

if __name__ == "__main__":
    main()
