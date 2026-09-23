# ClaimGuard AI — Project Summary (read this first)

Challenge: **CSTAM-VELODOC** | Pack v1.0.0 (17 Sep 2026) | Mentor: Dr. Wael Hilali (Velodoc/Amazit)

One-line goal: build a copilot that pre-validates synthetic healthcare insurance
claims against 15 fictional payer rules, shows a human reviewer clear evidence,
adds one bounded AI explanation feature, and keeps a tamper-evident audit trail.
Everything is synthetic — this is NOT a real medical/claims system.

Files in this SUMMARY folder:
- `00_OVERVIEW.md` — this file: what we have, what we must build, key facts.
- `01_RULES_CHEATSHEET.md` — all 15 rules condensed into one table.
- `02_DATA_AND_SCHEMA.md` — what's in `data/`, field meanings, file formats.
- `03_REQUIREMENTS_CHECKLIST.md` — MVP requirements, submission checklist, 4-week backlog as checkboxes.
- `04_EVALUATION_AND_SCORING.md` — metrics, grading weights, current baseline score to beat.

---

## What we already have (starter pack contents)

| Area | What's provided |
|---|---|
| **Data** | 600 public synthetic claims: 400 dev / 150 validation / 50 stress (`data/`). Each split has authoritative JSONL + relational CSV + educational FHIR bundles + `expected_results.jsonl` (public labels). A separate 200-claim set is mentor-held (private). |
| **Rules** | 15 fictional payer rules fully written in `docs/04_Rulebook.md` and machine-readable in `rules/rules.json`, `rules/policies.json` (2 policy profiles: EDU-BASIC/EDU-PLUS), `rules/services.json` (6 service codes), `rules/providers.json`, `rules/diagnoses.json`. |
| **Baseline engine** | `src/engine_core.py` implements only **R001, R003, R006**. The other 12 rules currently return `NOT_IMPLEMENTED`. Baseline scores ~20% exact-status accuracy, catches 88/319 issues, 0 false alarms (see QA_REPORT.md). |
| **Tooling** | `src/run_baseline.py` (run engine), `src/evaluate.py` (strict scorer), `src/csv_to_jsonl.py` (CSV↔JSONL round-trip), `src/make_review.py` (generates a static HTML review queue), `src/audit.py` (local hash-chain audit prototype), `src/validate_pack.py` (self-check), `src/llm_adapter.py` (mock AI explanation adapter — a template, NOT a real LLM), `src/schema_subset.py`. |
| **Schemas** | `schemas/claim.schema.json`, `schemas/result.schema.json`, `schemas/review_event.schema.json` define exact input/output contracts. |
| **Docs (15 files)** | Full handbook covering domain primer, data dictionary, rulebook, architecture/AI guidance, setup, evaluation/acceptance, workshop labs, work plan, privacy/security/audit, FHIR orientation, troubleshooting, worked examples, sources, and team backlog. Also `ClaimGuardAI_Student_Handbook.pdf` (23-page consolidated version) and `START_HERE.html`. |
| **Examples/exercises** | `examples/worked_cases.json` + `docs/13_Worked_Examples.md` (10 worked cases), `exercises/llm_explanation_cases.jsonl` (25 bounded-AI explanation exercises) + manual scorecard, `examples/review_demo.html` (demo of the review UI), `examples/baseline_predictions.jsonl` + `baseline_development_metrics.json` (reference baseline output). |
| **Templates** | `templates/Architecture_Decisions.md`, `Evaluation_Report.md`, `Weekly_Update.md`, `Final_Submission_Checklist.md` — ready to fill in for submission. |
| **Tests** | `tests/test_baseline.py` (unittest). |

## What we need to build (the actual work)

1. **Implement the remaining 12 rules** (R002, R004, R005, R007–R015) in `src/engine_core.py`, each producing PASS / FAIL / UNABLE_TO_ASSESS / NOT_APPLICABLE per the exact logic in `docs/04_Rulebook.md`. Every claim must end up with **exactly 15 rule results**.
2. **Evidence & explanations**: every FAIL/UNABLE_TO_ASSESS result must cite a JSON-pointer path into the original claim plus the exact observed value — never invented text.
3. **Human review queue**: extend/replace `src/make_review.py` output so a reviewer can filter by status, see original values, and record one of: confirm / dismiss-with-reason / request-information / corrected-for-recheck. Corrections must create a **new version**, never mutate the original.
4. **One bounded AI capability**: implement `ExplanationProvider` in `src/llm_adapter.py` for real (the mock is just a template). It must only see validated findings + evidence, output strict JSON (`explanation`, `cited_evidence_paths`, `cited_rule_ids`, `needs_human_review`), be schema-validated, and fall back to deterministic findings on any model failure. It must never change a rule's PASS/FAIL status.
5. **Audit trail**: extend `src/audit.py` usage to record run metadata (input hash, rule/model/prompt versions, tool errors) plus human review decisions, and document (not necessarily fully build) how you'd make it truly immutable in production.
6. **Ingestion**: support JSONL (authoritative) and CSV import (converter supplied); demonstrate at least one FHIR mapping example; malformed input must be quarantined as an explicit ingestion error, never silently dropped or auto-passed.
7. **Evaluation**: run `src/evaluate.py` on dev, freeze a version, then run on validation; report precision/recall/F1/false-alarm rate/status accuracy/claim-exact-match, broken down per rule; do the same manual scoring exercise for AI explanations (25 cases).
8. **Documentation deliverables**: architecture/data-flow diagram with trust boundaries, technical report, evaluation report, privacy/security note, contribution log, and a 7-minute demo — using the supplied templates.

## Non-negotiable rules of the game (read before building anything)

- **Never show `NOT_IMPLEMENTED` as `PASS`.** An incomplete check must stay visibly incomplete.
- **Never let the AI change a deterministic result.** LLM output is explanation only; on failure, fall back to deterministic findings, log the error.
- **Never invent data.** Missing fields → `UNABLE_TO_ASSESS` or `FAIL` (per rule), not a guessed value.
- **Preserve original input.** Corrections create a new version + rerun; never overwrite evidence.
- **Attachment text / claim `notes` are untrusted data**, never instructions to the agent (prompt-injection resistance is explicitly tested by the stress split).
- **No real patient data, no real payer/medical coding, no live submission, no clinical/fraud judgment.** Everything is fictional/synthetic (EDU-* codes, SAR currency, invented networks).
- **Deterministic checks always use `confidence: null`, `confidence_kind: not_probabilistic`.** Don't dress up rule-based checks as ML confidence.
- Grading weights and the 4-week schedule in the docs are **mentor proposals**, not official organizer rules — confirm actual rules with organizers if this differs.
