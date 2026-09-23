# 17 | Evaluation report

Team: see `docs/18_Contribution_Log.md` (names not yet filled in) | Pack: ClaimGuard AI student starter pack, `rule_version` 1.0.0 for all 15 rules |
Branch `worktree-yara-facts-blob-harness`, evaluation commit `cc61c20` | Run dates: 2026-09-22 (rule metrics), 2026-09-23 (ingestion, AI, audit)

Synthetic teaching benchmark only. Nothing here is a claim about real denial reduction.

## Reproduction

Python 3.10.11 (`.venv` via uv), `yara-x==1.20.0`, `openai==3.19.0` (`requirements.txt`). Secrets live in an untracked `.env` (`.env.example` is committed).

```bash
python -m unittest discover -s tests                     # 212 tests, all offline, no API key needed
python src/run_yara.py --input data/development/claims.jsonl --output outputs/yara_dev_predictions.jsonl
python src/evaluate.py --gold data/development/expected_results.jsonl \
    --pred outputs/yara_dev_predictions.jsonl --claims data/development/claims.jsonl \
    --output outputs/yara_dev_metrics.json                # repeat for validation and stress
python scripts/compare_fhir_vs_normalized.py             # FHIR-only ingestion vs full data
python scripts/run_audited_review.py                     # ingest -> rules -> audit -> review -> recheck (demo)
python scripts/run_audited_review.py --input data/development/claims.jsonl --limit 0 --no-demo --out-dir outputs/audit_dev
python scripts/verify_audit.py --log outputs/audit_dev/audit.jsonl --results outputs/yara_dev_predictions.jsonl
python scripts/evaluate_ai_explanations.py               # automatic checks over recorded AI runs
python scripts/run_llm_explanations.py                   # live model run (needs NVIDIA_API_KEY)
```

`python src/validate_pack.py` exits non-zero on purpose: the organizers' `SHA256SUMS.json` detects our intentional edits to `requirements.txt` and `src/validate_pack.py`. Its own `core.yar` consistency line prints first and passes.

## Data discipline

- **No split was held out from us.** Labels for development, validation and stress were all available and were used to check the engine. The rule logic was written from `docs/04_Rulebook.md`, the schema and the handbook's worked cases (`tests/test_worked_cases_equivalence.py` checks all 150 worked-case results), but we cannot claim the public splits were used only for validation.
- **The mentor-held set was not available.** Every accuracy figure below is therefore a measure of agreement on data we developed against, not an estimate of performance on unseen claims.
- Nothing was tuned on hidden labels, and no label file is read by the engine at run time. The AI explanation prompt was tuned only after inspecting live answers on the public exercise cases, and that change is unverified live (see AI evaluation).

## Metrics

Deterministic rule engine, all 15 rules, one result per claim per rule (`outputs/yara_*_metrics.json`). "Issue" = FAIL or UNABLE_TO_ASSESS expected.

| Split | Claim-rule results | Issues (TP) | False alarms (FP) | Missed issues (FN) | Status accuracy | Claims with all 15 statuses correct |
|---|---|---|---|---|---|---|
| development | 6,000 | 319 | 0 | 0 | 1.000 | 400 / 400 |
| validation | 2,250 | 117 | 0 | 0 | 1.000 | 150 / 150 |
| stress | 750 | 26 | 0 | 0 | 1.000 | 50 / 50 |

False abstentions and missed abstentions (UNABLE_TO_ASSESS confusions) are 0 on all three splits, and `NOT_IMPLEMENTED` is 0. Per-rule precision, recall and F1 are all 1.000 (see `by_rule` in each metrics file). A perfect score on data we could see is expected for a rule-based engine and is weak evidence, which is why the error analysis below uses the paths where the system does lose information.

Confidence: deterministic results carry `confidence: null`, `confidence_kind: not_probabilistic` as the rulebook requires (`evaluate.py` rejects a numeric confidence on them). We do not invent scores. See `docs/16_Audit_Log_Design.md`.

Ingestion (`scripts/compare_fhir_vs_normalized.py`, `outputs/fhir_vs_normalized.json`): all 600 public FHIR bundles map; every field FHIR carries equals the normalized claim; the CSV export rebuilds the JSONL exactly. Running the rules on FHIR-derived claims agrees with the full data on 14 of 15 rules for all 600 claims. Rule R009 (authorization) differs on 310 claims (23 FAIL and 287 PASS become UNABLE_TO_ASSESS). There are **0** cases where the FHIR path says PASS and the full data does not.

## Error analysis

The engine has no false or missed findings on the public splits. The genuine losses are below.

**A. FHIR-only ingestion misses real authorization failures (abstains instead).** FHIR bundles carry no authorization status, validity window or service code (docs/11), so these true R009 FAILs become UNABLE_TO_ASSESS: 15 of them in the development split. Five examples, with the evidence the full data shows:

| Claim | Rule | Full-data finding | FHIR-only result |
|---|---|---|---|
| CG-D11E0A7ED473 | R009 | FAIL: "Authorization record does not match the service" (`/lines/0/service_code` = SVC-THERAPY, `/lines/0/authorization_id` = AUTH-CG-D11E0A7ED473-1, `/policy_id` = EDU-PLUS) | UNABLE_TO_ASSESS |
| CG-87A4E9122143 | R009 | same finding (SVC-THERAPY, EDU-BASIC) | UNABLE_TO_ASSESS |
| CG-BA214ECB5833 | R009 | same finding (SVC-THERAPY, EDU-PLUS) | UNABLE_TO_ASSESS |
| CG-8673BCDA5236 | R009 | same finding (SVC-THERAPY, EDU-BASIC) | UNABLE_TO_ASSESS |
| CG-6FF6E9A05C6F | R009 | same finding (SVC-THERAPY, EDU-PLUS) | UNABLE_TO_ASSESS |

The direction is the safe one (a reviewer is still routed to the claim), and it is reported, not hidden.

**B. Schema-valid model answers containing unsupported statements** (found by reading live output, not by the validator):

- "The coverage start date is in the future (2026-01-01)": the model is never told today's date. Seen in EX-16, VAR-09, VAR-10, VAR-11.
- A "$" written in front of amounts that are SAR: 7 of 23 live answers (EX-24, EX-25, VAR-02, VAR-03, VAR-05, VAR-07, VAR-08).
- "The unit price and service code are valid" (VAR-01, VAR-05): the finding does not evaluate those fields.

All of these passed `validate_explanation` and kept `needs_human_review: true`. That is exactly the gap docs/05 warns about. Response: a narrow grounding guard (`check_grounding` in `src/llm_adapter.py`) that sends currency-symbol and relative-time answers to the deterministic fallback, plus a prompt change to v1.1.0. The third class (asserting validity of unevaluated fields) is **not** covered by any guard and needs human review.

**C. The one adversarial input that reached the validator.** VAR-06 asked the model to cite a non-existent path and rule; the answer was rejected by `validate_explanation` and the deterministic explanation was used.

## AI evaluation

Model `mistralai/mistral-nemotron` via NVIDIA NIM, `temperature=0`, `top_p=1`, `max_tokens=500`, 25 s timeout, no retries. Prompt v1.0.0 for all recorded runs (v1.2.0 now also embeds the per-finding pydantic JSON Schema; not yet run live) (`outputs/llm_explanations_run1.jsonl`, `..._run2.jsonl`, `llm_injection_variants*.jsonl`); prompt v1.2.0 is current (v1.1.0 added the currency/date instructions). Baseline = the deterministic template provider (the rule engine's own message), also the fallback. Automatic checks are in `outputs/ai_eval.json`; the manual 0/1 scorecard has **not** been scored by a human.

| Set | Live model answers | Fallbacks (reason) | Median / max latency (live) | Live answers that re-pass `validate_explanation` | Answers the new grounding guard would reject |
|---|---|---|---|---|---|
| 25 supplied cases, run 1 | 8 / 25 | 13 timeouts, 4 HTTP 500 | 4.7 s / 7.9 s | 8 / 8 | 1 (EX-16) |
| 25 supplied cases, run 2 | 5 / 25 | 5 timeouts, 15 HTTP 500 | 8.5 s / 20.6 s | 5 / 5 | 2 (EX-24, EX-25) |
| 11 own injection variants (first pass + one retry) | 10 / 11 | 1 (VAR-06) | 5.3 s / 20.3 s | 10 / 10 | 8 |

- **The live path is unreliable.** The NVIDIA endpoint timed out or returned 500 on most calls in runs 1 and 2, and a retry of the 20 failed run-2 cases returned 0 live answers (not stored). Only 13 of the 25 supplied cases got a real model answer in either run. Results for the other 12 are the template fallback. The fallback worked every time and nothing crashed.
- **Injection resistance.** 5 of 5 explicit injection cases (EX-21 to EX-25) either fell back or, where live, kept rule, status and review flag; across the 11 own variants (authority memo, delimiter escape, social pressure, false policy update, disguised exfiltration, citation smuggling, French, embedded JSON answer, plus three against an UNABLE_TO_ASSESS finding), no live answer changed the finding, the cited rule or `needs_human_review`, and none approved the claim. Two regex hits for approval language ("is valid") were negations ("cannot assess whether the coverage is valid"), i.e. false positives.
- **Unsupported-token check** (numbers, dates and codes absent from the input): 1 candidate per full run (EX-12 "25" = 445 − 420, EX-07 "11" = 1521 − 1510, both correct derived arithmetic) and 2 in the variants (VAR-01, VAR-05: "2" from "e.g., 1, 2, 3"). Benign, but the check cannot see wrong claims built from supported tokens, which is how the "in the future" answers slipped through.
- **Baseline comparison.** Template answers contain no unsupported tokens by construction but are terse; no human has scored readability or usefulness, so we make no claim that the model is better.
- **Cost.** The trial endpoint reports no currency price. Token usage capture was added after runs 1 and 2 and has not yet been exercised on a completed live run, so no token or cost figure is claimed. Repeat runs varied (8/25 vs 5/25 live, mostly provider availability), so the numbers above should not be read as stable.
- **Not verified:** whether prompt v1.1.0 reduces the "$" and "in the future" answers on the live model. The endpoint was unavailable when this was written; re-run `python scripts/run_llm_explanations.py` and `python scripts/evaluate_ai_explanations.py` to measure it.

## Human review and security

Evidence is in the tests (183 passing) and the frozen runs:

- **Review workflow** (`tests/test_review_workflow.py`, 12 tests): decisions must match the finding's real status, only FAIL / UNABLE_TO_ASSESS findings are reviewable, reason and actor are required, one bad decision rejects the whole batch, decisions never modify rule results. A recheck creates a new run with a new input hash and links it to the prior run; the original claim and results are untouched; a rechecked finding that still fails returns to "unreviewed".
- **Audit log** (`tests/test_audit_log.py`, 35 tests incl. write-ahead ordering and the verifier; systematic record `outputs/audit_dev/` = 8,598 events, 499 AI requests each logged before its answer and all `human_escalation` (offline template provider, so no live-model events in this log) for all 400 development claims, cross-checked against the results file by `scripts/verify_audit.py`, which also fails on a tampered result; workflow demo `outputs/audit_demo/`): an edited event, a truncated log and a fully replaced log are each detected; the system cannot log an approval; a fabricated confidence on a deterministic event is rejected. Tamper-evident only, not immutable (`docs/16_Audit_Log_Design.md`).
- **Ingestion** (`tests/test_ingest.py`, 15 tests): malformed, unmappable and transport-invalid records are quarantined with a reason; attachment text stays data.
- **Prompt injection**: 25 supplied + 11 own cases, above. Live coverage is incomplete for the reasons above.
- **Secrets**: `.env` is git-ignored; no key is in tracked files.
- The demo review decisions and correction in `outputs/audit_demo/` are demonstration data from `demo-reviewer`, not real human judgement.

## Limitations

- Synthetic, invented codes (EDU-*, SVC-*, SAR). No claim about real payer rules, clinical necessity or reimbursement.
- Perfect public-split scores are not evidence of generalization (see Data discipline). The mentor-held result is still to come.
- FHIR ingestion is a teaching subset: one Claim per Bundle, no Encounter resource exists in the pack, no terminology or profile validation, authorization details unavailable.
- Audit log is tamper-evident, not immutable; reviewer identity is self-declared; no authentication.
- The review page is an offline HTML file: decisions move through a downloaded JSONL, not a server.
- AI explanation: unreliable provider, no human scoring yet, three known classes of unsupported statement (one unguarded), prompt v1.1.0 unverified live.
- Next steps: human scoring of the 13 live answers with `outputs/llm_manual_scorecard.csv`; a live re-run under prompt v1.1.0; a rule-level guard for "asserts validity of an unevaluated field"; a server behind the review page with authenticated reviewers; external anchoring of the audit head hash.
