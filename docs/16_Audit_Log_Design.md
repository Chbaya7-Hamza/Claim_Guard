# 16 | Audit log design

Code: `src/audit_log.py` (system events, anchor), `src/audit.py` (supplied; reviewer
decisions, chain verifier), `src/review_workflow.py` (decision validation, recheck).
Sample run: `python scripts/run_audited_review.py` writes `outputs/audit_demo/` (workflow demo). Systematic record over a whole split: `--limit 0 --no-demo` (see README), committed as `outputs/audit_dev/` (8,598 events, 400 claims). `python scripts/verify_audit.py --log ... --results ...` checks the chain, the anchor and that every result's hash is in the log.

## What is recorded

One append-only JSONL chain. Every row is `{sequence, recorded_at, previous_hash, event, hash}`
where `hash = SHA-256(canonical JSON of the row without hash)`.

| event | written by | contents |
|---|---|---|
| `ingestion` | system | claim id, source format, accepted / quarantined (+ error) |
| `run_started` | system | run id, claim id, SHA-256 of the input claim |
| `rule_check` | system | one per rule: rule id + version, status, severity, affected lines, **hash of the full result record**, `confidence: null`, `confidence_kind: not_probabilistic`, `method: deterministic` |
| `ai_request` | system, **written before the model is called** | the question put to the AI: request id, rule id, the deterministic status it was asked about and the plain-language `verdict` (`violation_detected` / `cannot_determine`), hash of the finding, prompt version and **hash of the exact prompt**, hash (never the text) of any untrusted note, provider/model, and the `action_type` |
| `ai_recommendation` | system, after the call | linked by `request_id`: model (or `deterministic-template`), `source` (`model` or `deterministic_template`), fallback flag and error, latency, token usage, hash + text of the explanation, `action_type: human_escalation`, `escalated_to: human_reviewer`, `auto_correct_applied: false`, `confidence: null` |
| `ai_failure` | system | the AI step itself failed (both primary and fallback): the request is still answered, with the error |
| `system_decision` | system | `route_to_human_review`, `no_findings_for_review` or `quarantine_claim`. The system cannot record an approval or denial; a clean claim is logged as "not an approval". |
| `run_finished` | system | rule pack hash, rule versions, tool errors |
| `confirm_issue` / `dismiss_with_reason` / `request_information` / `mark_corrected_for_recheck` | human (via review workflow) | actor, reason, `original_status`, timestamp |
| `recheck_run` | system | links `prior_run_id` -> `new_run_id` and both input hashes |

Reviewer decisions are validated against the *actual* finding before they are written
(status must match, only FAIL / UNABLE_TO_ASSESS findings are reviewable, reason and
actor required, batch is all-or-nothing). Decisions never modify rule results.
A correction is a **new version and new run**; the original claim, results and run
stay in the log untouched.

## What is registered before the AI acts, and how the AI's action is classified

`audited_review()` (`src/audit_log.py`) is write-ahead: each stage is appended to the log before
the next runs. The order per claim is `ingestion`, `run_started`, all 15 `rule_check` events (the
deterministic verdicts), then for every FAIL / UNABLE_TO_ASSESS finding an `ai_request`, **then**
the model call, then `ai_recommendation` (or `ai_failure`), and finally `system_decision` and
`run_finished`. If the `ai_request` cannot be written (disk error), the exception aborts the run and
the model is never called (`tests/test_audit_log.py::WriteAheadTests`). A test provider that reads the
log file at the instant it is called confirms the request is already durable and unanswered.

The "question" is recorded as data, not free text from a user: the rule, the deterministic status the
AI was asked to explain, the verdict in plain terms, and hashes of the finding and the exact prompt
(so the request can be reproduced and checked). Untrusted claim notes are stored by hash only.

**Every AI action is `human_escalation`.** The model drafts an explanation and the finding goes to a
person; it never edits a claim or a result. `auto_correct` is not a permitted value: an event carrying it,
or `auto_correct_applied: true`, is rejected at write time, and `verify_ai_ordering()` fails a log that
contains one. PASS and NOT_APPLICABLE findings get no AI action at all.

`python scripts/verify_audit.py --log <log>` re-checks all of this from the log alone: every AI outcome has an
earlier matching request, was answered once, is recorded no earlier than its request, the request came after the
rule check it refers to (with the same status), and no run finished with an unanswered request. Limit: this proves
the *log's* ordering, and relies on the log writer being the code path that calls the model (a caller that bypassed
`audited_review()` would leave no record at all, which is what external anchoring and access control are for).

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

Opening an existing log with an anchor re-checks it against the anchor first, so a truncated log is rejected instead of being silently re-anchored (`tests/test_audit_log.py`).

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
