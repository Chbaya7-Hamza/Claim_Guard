# 16 | Audit log design

Code: `src/audit_log.py` (system events, anchor), `src/audit.py` (supplied; reviewer
decisions, chain verifier), `src/review_workflow.py` (decision validation, recheck).
Sample run: `python scripts/run_audited_review.py` writes `outputs/audit_demo/`.

## What is recorded

One append-only JSONL chain. Every row is `{sequence, recorded_at, previous_hash, event, hash}`
where `hash = SHA-256(canonical JSON of the row without hash)`.

| event | written by | contents |
|---|---|---|
| `ingestion` | system | claim id, source format, accepted / quarantined (+ error) |
| `run_started` | system | run id, claim id, SHA-256 of the input claim |
| `rule_check` | system | one per rule: rule id + version, status, severity, affected lines, **hash of the full result record**, `confidence: null`, `confidence_kind: not_probabilistic`, `method: deterministic` |
| `ai_recommendation` | system | rule id, model (or `deterministic-template` on fallback), prompt version, `used_fallback`, validator/provider error, latency, token usage, hash + text of the explanation, `confidence: null` |
| `system_decision` | system | `route_to_human_review`, `no_findings_for_review` or `quarantine_claim`. The system cannot record an approval or denial; a clean claim is logged as "not an approval". |
| `run_finished` | system | rule pack hash, rule versions, tool errors |
| `confirm_issue` / `dismiss_with_reason` / `request_information` / `mark_corrected_for_recheck` | human (via review workflow) | actor, reason, `original_status`, timestamp |
| `recheck_run` | system | links `prior_run_id` -> `new_run_id` and both input hashes |

Reviewer decisions are validated against the *actual* finding before they are written
(status must match, only FAIL / UNABLE_TO_ASSESS findings are reviewable, reason and
actor required, batch is all-or-nothing). Decisions never modify rule results.
A correction is a **new version and new run**; the original claim, results and run
stay in the log untouched.

## Confidence scores

The rulebook (docs/04, docs/05) requires deterministic checks to carry
`confidence = null` with `confidence_kind = not_probabilistic`; a model's self-reported
score is uncalibrated and must be labelled so. `evaluate.py` rejects a numeric
confidence on a deterministic result. The field is present and machine-readable on
every finding and every audit event, and we do not invent numbers to fill it. Our
explanation contract returns no score, so AI events also record null. If a
model score were added later it would be stored with `confidence_kind: uncalibrated`.

## Tamper evidence: what this does and does not give you

Guaranteed:
- Editing, deleting or reordering any event in the middle breaks the chain
  (`audit.verify`, `audit_log.verify_with_anchor`).
- Each `rule_check` carries the hash of the result record it summarises, so a stored
  results file can be checked against the log.
- The head hash and event count are written to `<log>.head.json`. Comparing the log
  with a separately held copy of that file detects **truncation** and **whole-log
  replacement** (tested in `tests/test_audit_log.py`).

Not guaranteed - this is tamper-*evident*, not immutable:
- Anyone with write access to both the log and the anchor can rewrite history and
  recompute every hash. There is no signature key and no authentication;
  reviewer identity is a self-declared string.
- The anchor only helps if it is stored somewhere the log writer cannot modify.

What real immutability would need (not built):
- Storage the application cannot alter: an object store with object-lock / WORM
  retention, or a database role limited to INSERT.
- The head hash periodically published to an external timestamping or transparency
  service, or signed with a key held outside the application.
- Authenticated reviewers (SSO) so `actor` is not self-declared.
- Retention and access-control policy for the log itself, including redaction rules
  (the log holds synthetic data here; real claims would make the log sensitive).
