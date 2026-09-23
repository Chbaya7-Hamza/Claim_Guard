# ClaimGuard AI | Student starter pack

**Start here.** Build a trustworthy copilot that pre-validates synthetic healthcare claims and supports human review.

Version 1.0.0 | CSTAM-VELODOC | Mentor: Dr. Wael Hilali

## Your first 30 minutes

1. Read docs/01_Challenge_Brief.md and docs/02_Claims_Primer.md.
2. Open examples/review_demo.html in a browser to see the review workflow.
3. Read one case in docs/13_Worked_Examples.md and its full input in examples/worked_cases.json.
4. Follow docs/06_Setup_and_First_Run.md. No paid account or extra Python packages are needed.
5. Agree team roles and the first three tasks with your mentor.

## What is included

- 600 unique public claims: 400 development, 150 validation, 50 stress.
- Normalized JSONL, relational CSV and educational FHIR R4-style projections.
- 15 fictional payer rules, two policy profiles, six service codes, public expected results.
- Ten worked examples and 25 bounded-AI explanation exercises.
- A runnable three-rule baseline, strict evaluator, CSV converter, local review page and audit prototype.
- Input/output schemas, prompt template, model-neutral mock adapter, tests and validation checks.
- Full handbook, workshop labs, roadmap, editable reporting templates and security guidance.

## Quick run (from this folder)

```bash
python src/validate_pack.py
python -m unittest discover -s tests -v
python src/run_baseline.py --input data/development/claims.jsonl --output outputs/dev_predictions.jsonl
python src/evaluate.py --gold data/development/expected_results.jsonl --pred outputs/dev_predictions.jsonl --claims data/development/claims.jsonl --output outputs/dev_metrics.json
python src/make_review.py --input outputs/dev_predictions.jsonl --output outputs/review.html
```

Open outputs/review.html. On Windows use py, or on macOS/Linux python3, if python is unavailable. See docs/06 for details.

## Our team's complete 15-rule implementation

The commands above run the **supplied** three-rule baseline (`engine_core.py` /
`run_baseline.py`), left untouched on purpose so it stays the known-good
reference the starter pack ships with (`outputs/dev_metrics.json`,
`status_accuracy≈0.2`, R001/R003/R006 only — 12 rules `NOT_IMPLEMENTED`).

Our team's implementation of **all 15 rules** lives in a separate, additive
engine and does not modify any supplied starter file:

- `src/facts_extractor.py` — one `rXXX_details()` function per rule (single
  source of truth for its fact tags, evidence paths, line ids and message)
- `rules/core.yar` — a compiled YARA-X rule pack that classifies each rule's
  outcome (FAIL / UNABLE_TO_ASSESS / NOT_APPLICABLE / PASS) from those facts
- `src/yara_engine.py` — compiles the pack, scans, resolves precedence, and
  assembles full `schemas/result.schema.json`-shaped results
- `src/run_yara.py` — the CLI entry point that runs it over any claims split

To reproduce our full-rule results and metrics:

```bash
python src/run_yara.py --input data/development/claims.jsonl --output outputs/yara_dev_predictions.jsonl
python src/evaluate.py --gold data/development/expected_results.jsonl --pred outputs/yara_dev_predictions.jsonl --claims data/development/claims.jsonl --output outputs/yara_dev_metrics.json
python src/make_review.py --input outputs/yara_dev_predictions.jsonl --output outputs/yara_review.html
```

Frozen results (`outputs/yara_dev_metrics.json`, `yara_validation_metrics.json`,
`yara_stress_metrics.json`, committed): **`status_accuracy = 1.0`, `issue_precision = 1.0`,
`issue_recall = 1.0`** across all three public splits (9,000/9,000 claim-rule
results), plus an exact match against the handbook's own 10 worked-case oracle
in `examples/worked_cases.json` (`tests/test_worked_cases_equivalence.py`).
Run `python -m unittest discover -s tests -v` (102 tests) to verify.

**Expected, not a bug:** `python src/validate_pack.py` prints a
`rules/core.yar compiles and matches rules.json` PASS line for all 15 rules,
then exits non-zero with `AssertionError: Release checksum differs:
requirements.txt`. `SHA256SUMS.json` is the original release-integrity
manifest; we intentionally edited `requirements.txt` (added the `yara-x`
dependency) and `src/validate_pack.py` (added the `core.yar` check) — both
files it tracks — so that block correctly detects the change and raises, per
its own message. We never edit `SHA256SUMS.json` itself.

## Read in this order

01 brief; 02 domain; 03 data contract; 04 rulebook; 06 setup; 13 examples; 05 architecture/AI; 07 evaluation; 08 workshop; 09 work plan; 10 security; 11 FHIR; 12 troubleshooting; 14 sources.

## Scope and honesty

All records and policies are synthetic. The baseline covers only R001/R003/R006; other checks are explicitly NOT_IMPLEMENTED. The mock adapter is not an LLM. The local hash chain is tamper-evident, not immutable storage. FHIR examples are educational mappings without full HL7/profile validation. Passing these fictional rules is not payer approval or evidence of production readiness.

Ask the mentor for model access before the AI milestone. Never place credentials or real patient records in this repository. Follow organizer instructions if they differ from suggested schedules or grading weights here.
