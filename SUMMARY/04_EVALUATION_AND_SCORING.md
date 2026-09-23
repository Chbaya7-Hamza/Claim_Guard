# Evaluation, Scoring & Current Baseline

Source of truth: `docs/07_Evaluation_and_Acceptance.md`, `QA_REPORT.md`, `data/dataset_manifest.json`.

## Protocol

1. Develop against the 400 `data/development` claims.
2. **Freeze a commit** before your first validation run.
3. Run against the 150 `data/validation` claims to find gaps. Once validation labels have influenced your development, you must **disclose** that validation became development feedback (i.e., don't silently re-tune forever and call it a validation score).
4. The 50 `data/stress` claims test robustness (boundaries, uncertainty, untrusted text) — not a representative issue-rate sample.
5. The mentor privately holds 200 more claims for final assessment.

The strict scorer (`src/evaluate.py`) requires **every claim-rule pair exactly once**. It rejects: missing pairs, extra pairs, duplicates, invalid statuses, mismatched evidence values. `NOT_IMPLEMENTED` counts against your accuracy — you cannot skip claims to dodge scoring.

## Metrics computed

| Metric | Meaning |
|---|---|
| Issue precision | true predicted FAIL / all predicted FAIL |
| Issue recall | true predicted FAIL / all expected FAIL |
| Issue F1 | harmonic mean of the above |
| False-alarm rate | predicted FAIL among pairs whose expected status ≠ FAIL |
| Status accuracy | exact match across PASS/FAIL/UNABLE_TO_ASSESS/NOT_APPLICABLE |
| False abstentions | predicted UNABLE_TO_ASSESS when expected was something else |
| Missed abstentions | expected UNABLE_TO_ASSESS but predicted something else |
| Claim exact match | all 15 rule statuses correct for one claim |

Undefined precision/recall → reported as `null`, never treated as 100%. All metrics at claim-rule level unless labeled otherwise. Always inspect **per-rule** results — overall accuracy hides rare failures. Note: evidence-value matching does not by itself prove the evidence field is actually relevant to the conclusion.

## Proposed mentor grading weights (proposal, confirm at kickoff)

| Area | Weight | What's inspected |
|---|---|---|
| Rule correctness | 35% | per-rule results; date/amount/authorization edge cases |
| Grounded AI explanations | 20% | the 25 supplied exercise cases + fresh variants; no unsupported approvals |
| Human review & usability | 15% | reviewer can trace findings, dismiss with reason, request info, trigger recheck |
| Uncertainty & security | 15% | unknown data, malicious document text, tool errors, access boundaries |
| Audit & reproducibility | 10% | trace hashes/versions, audit history, repeatable install |
| Communication | 5% | concise architecture, limitations, demo |

## Non-negotiable demonstration checks

- No unimplemented/unknown check is ever shown as a pass.
- Every flagged issue links to source evidence + the applicable fictional rule.
- A model failure can never remove a deterministic finding.
- Original input is preserved; a correction is rechecked as a new version.
- No real patient info, exposed credential, or live payer submission appears in the demo.

## AI evaluation procedure

1. Run baseline with template explanations, then your model-assisted version, on the same cases.
2. Manually score each explanation 0/1 on: correct finding, correct evidence, correct rule, appropriate action, honest uncertainty.
3. Record unsupported statements separately.
4. Report: model identifier, prompt version, parameters, latency, failures, measured cost.
5. Report repeat-run variance if outputs differ between runs.
6. **Never tune on the hidden (mentor-held) labels.**

## Current baseline to beat (from QA_REPORT.md, dev split)

- Implements only R001, R003, R006 → 1,200 real results + 4,800 `NOT_IMPLEMENTED` out of 6,000 total.
- Catches **88 of 319** expected issue pairs.
- **Zero false alarms** on the synthetic dev set.
- **~20% exact-status accuracy** overall (dominated by the NOT_IMPLEMENTED penalty).

## Dataset label distribution (dataset_manifest.json) — sanity-check target

| Split | PASS | NOT_APPLICABLE | UNABLE_TO_ASSESS | FAIL | Total rows |
|---|---|---|---|---|---|
| development (400 claims) | 5,014 | 487 | 180 | 319 | 6,000 |
| validation (150 claims) | 1,879 | 181 | 73 | 117 | 2,250 |
| stress (50 claims) | 599 | 63 | 62 | 26 | 750 |

Use this table to sanity-check your engine: e.g., on dev your R001 output should land near 364 PASS / 36 FAIL (no NOT_APPLICABLE / UNABLE_TO_ASSESS possible for that rule), R008/R009/R010 should show large NOT_APPLICABLE counts (~159/400) since most claims don't need authorization or documents, etc. Full per-rule breakdown is in `data/dataset_manifest.json`.
