# Requirements & Submission Checklist

Source of truth: `docs/01_Challenge_Brief.md`, `docs/09_Work_Plan_and_Templates.md`, `docs/15_Team_Backlog.md`.
Reminder: the schedule/weights here are **mentor proposals**, not an official organizer timetable — confirm with organizers if different.

## Required MVP behaviour (from the challenge brief)

- [x] Ingest normalized JSONL (authoritative); support CSV import (converter supplied). ⚠️ FHIR mapping example is only structural (validate_pack.py's bundle checks) — no dedicated walkthrough/demo yet.
- [x] Evaluate **all 15** documented fictional rules, including uncertainty (`UNABLE_TO_ASSESS`) and `NOT_APPLICABLE` outcomes. `src/facts_extractor.py` + `rules/core.yar` + `src/yara_engine.py`; run via `src/run_yara.py`. Verified `status_accuracy=1.0`, `issue_precision=1.0`, `issue_recall=1.0` across all three public splits (9,000/9,000 results) plus the handbook's 10-case worked-examples oracle (150/150). See `README.md` → "Our team's complete 15-rule implementation".
- [x] Report per finding: Claim ID, Rule ID/version, severity, affected lines, evidence, explanation, corrective action. Every field present in every `yara_engine.evaluate()` result; verified against `schemas/result.schema.json` via `src/evaluate.py`'s strict scorer.
- [x] Review queue with filters, original values shown, and clear unresolved-check counts. Supplied `make_review.py` — verified it renders against the full 15-rule output (`outputs/yara_review.html`).
- [x] Support 4 review decisions: confirm / dismiss-with-reason / request-information / corrected-for-recheck. Supplied in `make_review.py`. ⚠️ Not yet exercised end-to-end — no `review_decisions.jsonl`/`audit.jsonl` produced yet.
- [ ] One bounded AI capability (plain-language explanation or reviewer handover) grounded in validated findings, with visible tool boundaries, schema checks, and a safe fallback. AI must never relabel a deterministic result. **Not started** — `src/llm_adapter.py` is still the mock template. Next up.
- [ ] Record checks + human actions with source/rule/model versions; tamper-evident audit prototype; explain what's still needed for real immutability. Audit prototype (`audit.py`) supplied and working, but nothing records run-level trace metadata (input hash, rule/model/prompt versions) yet.
- [~] Evaluate on provided data, then report against the mentor-held set; report false alarms, missed issues, and uncertainty handling **separately**. Done for all 3 public splits (dev/validation/stress — see per-split `outputs/yara_*_metrics.json`, each reports precision/recall/false-alarm/abstention separately per the metric definitions in docs/07). Mentor-held 200-claim set is private by design — outside our control.

## Scope boundaries (do NOT do these)

- No real clinical diagnosis or medical-necessity judgment.
- No fraud accusation.
- No automatic claim approval.
- No live payer submission.
- No EHR integration.
- Everything uses invented educational codes (EDU-*, SVC-*, SAR currency) — not real coding standards.

## Submission checklist (final deliverables)

- [ ] Reproducible repo: README, dependencies, config example, launch commands.
- [ ] Architecture & data-flow diagram showing trust boundaries and tool permissions.
- [ ] Working review interface + recorded demo + concise pitch presentation.
- [ ] Technical report: implementation, decisions, tests, limitations.
- [ ] Evaluation report: dataset split, per-rule metrics, false positives/negatives, AI ablations.
- [ ] Privacy/security note + auditable sample run. No secrets in the repo.
- [ ] Contribution log: team roles + how AI coding tools were used.

Use the ready-made templates for these: `templates/Architecture_Decisions.md`, `templates/Evaluation_Report.md`, `templates/Weekly_Update.md`, `templates/Final_Submission_Checklist.md`.

## Suggested 4-week plan

| Week | Focus | Exit evidence |
|---|---|---|
| 1 | Understand data; run baseline; core validation | Reproducible setup, data map, first tests, review screenshot |
| 2 | Complete all 15 rules; evidence + uncertainty handling | Per-rule metrics, edge-case tests, complete structured outputs |
| 3 | Bounded AI; review workflow; audit | Grounded explanation examples, failure fallback, human action trace |
| 4 | Evaluation; hardening; docs; demo | Frozen version, error analysis, demo video, report, pitch |

## Team backlog (dependency order — from docs/15)

- [x] **T01** — Run baseline, tests, validation → verified: `python -m unittest discover -s tests -v` (102 tests OK), `python src/validate_pack.py` (all splits + core.yar PASS).
- [ ] **T02** — Manually explain 3 worked cases without looking at labels → findings with pointers + rule IDs. (Process/learning exercise, not code — still open.)
- [x] **T03** — Implement R002, R004, R005 → `tests/test_facts_extractor_r00{2,4,5}.py`, positive/negative/unknown each.
- [x] **T04** — Implement R007, R012, R015 → `tests/test_facts_extractor_r0{07,12,15}.py`, decimal/tolerance + currency mismatch cases.
- [x] **T05** — Implement R011, R013 → `tests/test_facts_extractor_r0{11,13}.py`, unknown code, limit boundary, invalid quantity cases.
- [x] **T06** — Implement R008, R009 → `tests/test_facts_extractor_r00{8,9}.py`, missing reference, absent record, aggregate-limit, uncatalogued-code cases.
- [x] **T07** — Implement R010, R014 → `tests/test_facts_extractor_r0{10,14}.py`, document identity/status + submission-window boundary cases.
- [x] **T08** — Produce all 15 results per claim → `src/run_yara.py` + `src/evaluate.py` accept a complete run on all 3 public splits, `status_accuracy=1.0`.
- [ ] **T09** — Real model explanation adapter + fallback (`src/llm_adapter.py`) → manual scorecard + invalid-output tests. **Next up.**
- [ ] **T10** — Review queue + correction/recheck workflow → source and decisions stay separate. UI exists and renders (`make_review.py`); not yet exercised to produce a real decisions file.
- [ ] **T11** — Run-level trace metadata → input hash, rule/model/prompt versions, tool errors. Not started.
- [ ] **T12** — Freeze + evaluate a release → versioned report, error analysis, demo. Rules are frozen/evaluated (`outputs/yara_*_metrics.json`); the written report/demo deliverables are still open.

**Stretch goals (after core MVP only):** FHIR ingestion adapter with explicit unsupported-field list; policy-version switching; comparison of two AI explanation approaches; authenticated review; durable audit design. Do **not** expand into real patient data, clinical decisions, or live submission.

## Definition of done for each rule

A rule is "done" only when it is: documented, implemented, emits the correct schema, references original evidence, handles nulls/boundaries correctly, has at least one positive/negative/unknown test, and has been reviewed by a teammate. Log any rule-behavior clarification in a versioned decision log before changing expected behavior.

## Suggested 7-minute final demo structure

1. min 1 — problem & scope
2. min 2 — a clean claim + a claim with clear issues
3. min 1 — uncertainty case + information request
4. min 1 — grounded AI explanation + its fallback
5. min 1 — evidence, review, and audit trail
6. min 1 — measured results, limitations, next steps

Never claim a real denial-reduction percentage from this synthetic exercise — report only which administrative errors your system detects, and how you measured it.
