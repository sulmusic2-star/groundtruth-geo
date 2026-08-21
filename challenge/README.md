# GroundTruth-Geo blind challenge

This package separates four events that must not be conflated:

1. **Committed:** question, protocol, schema, and salted gold hashes were fixed.
2. **Submitted:** an outside participant returned predictions and the exact file hash was frozen.
3. **Scored:** the private custodian ran the fixed scorer after submission.
4. **Independently reviewed:** an unaffiliated, qualified reviewer examined the evidence and method and signed the attestation.

A local run, a self-signature, or a vendor model API response can satisfy technical testing but cannot satisfy step 4.

The participant receives only `questions.jsonl`, `prediction-schema.json`, the protocol, and the blank attestation. Lasting Ground retains the item map, gold, evidence, nonce, and detailed score privately. Public receipts contain hashes and aggregate scores, never the private cases.

NIST's AI RMF Playbook recommends documenting test sets, metrics, and TEVV tools, involving independent assessors or teams separate from front-line developers, and assessing whether those actors have enough independence and resources. This workflow implements the technical separation while leaving the human independence gate explicit.
