# ClaimGuard AI | Student starter pack

**Start here.** Build a trustworthy copilot that pre-validates synthetic healthcare claims and supports human review.

Version 1.0.0 | CSTAM-VELODOC | Mentor: Dr. Wael Hilali

## Phase 1 deliverables: where each rubric item lives

| Rubric item | Where it is | Verify |
|---|---|---|
| **Data ingestion and normalization** (FHIR R4 JSON / CSV to one internal form) | `src/ingest.py` (format detection, quarantine), `src/fhir_adapter.py`, `src/csv_to_jsonl.py`; envelope `schemas/claim.schema.json` | `python src/ingest.py --input data/development/fhir_bundles.jsonl --output outputs/ingest_normalized.jsonl --report outputs/ingest_report.json` |
| **Deterministic and AI rule engine** (15 fictional rules) | `rules/core.yar` + `rules/rules.json`, `src/yara_engine.py`; bounded AI in `src/llm_adapter.py` | `python src/run_yara.py` ; metrics in `outputs/yara_*_metrics.json` |
| **Explainability and structured output** | `schemas/result.schema.json`; every result is validated against it | `python -m unittest tests.test_phase1_rubric` |
| **Audit log engine** | `src/audit_log.py`, design in `docs/16_Audit_Log_Design.md` | `python scripts/verify_audit.py --log outputs/audit_dev/audit.jsonl --results outputs/yara_dev_predictions.jsonl` |

**Entities the rubric names, and where each is carried**

| Entity | FHIR R4 bundle | CSV folder | Normalized field |
|---|---|---|---|
| Patient | `Patient` (member id in `identifier`) | `claims.csv` | `patient_id`, `member_id` |
| Encounter | **not in the supplied pack.** `fhir_adapter` reads any `Encounter` a bundle does carry into the ingest report (`encounters`), with warnings for a patient mismatch or a dangling `item.encounter`. It is not part of the claim envelope, and no rule uses it. | none | none (the closed claim schema has no slot) |
| Coverage | `Coverage` | `coverage.csv` | `coverage{}` |
| Provider | `Organization` referenced by `Claim.provider` | `claims.csv` | `provider_id` |
| Diagnosis | `Claim.diagnosis` | `claims.csv` | `diagnosis_code` |
| Claim line items | `Claim.item[]` | `lines.csv` | `lines[]` |

The FHIR route cannot carry authorization details or free-text notes, so R009 returns `UNABLE_TO_ASSESS` there instead of guessing (310 of 600 claims); it is never shown as a pass.

**The 15 rules, by what they detect**

| Detects | Rules |
|---|---|
| Missing data | R001 required fields; R008 authorization reference; R010 supporting document |
| Inconsistent data | R002 dates in order; R003 coverage on service date; R004 member/beneficiary; R007 line arithmetic; R009 authorization matches service; R012 claim total; R015 currency |
| Duplicate data | R006 repeated service line |
| Unsupported data | R005 provider not in network; R011 unknown service code; R013 quantity/price limits; R014 outside submission window |

**Structured output.** The rubric's fields map to the result schema as: Claim ID = `claim_id`, Rule ID = `rule_id` (+ `rule_version`), rule-linked evidence = `evidence` (JSON-pointer path plus the observed value) and `rule_source`, severity level = `severity`, suggested corrective action = `corrective_action`, confidence score = `confidence` with `confidence_kind`. Per `docs/04_Rulebook.md` ("Deterministic checks use confidence=null and confidence_kind=not_probabilistic"), rule results carry `confidence: null`, exactly as the supplied answer key does on all 6,000 development results; an invented score would be presented as a probability it is not. A model-reported score would be stored as `uncalibrated`. The AI explanation contract carries no score.

**Audit log.** It records ingestion, every rule check with its confidence fields, the AI's question (written before the model is called), the AI recommendation, and system and human decisions, as a hash chain plus a separately stored head-hash anchor. This is tamper-*evident*, not immutable: `docs/16_Audit_Log_Design.md` states what production immutability would additionally need (write-once storage, an externally held anchor, authenticated reviewers).

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
Run `python -m unittest discover -s tests -v` (all tests, offline, no API key) to verify.

## Bounded AI explanation (`src/llm_adapter.py`)

We added a `.venv` (managed with [`uv`](https://docs.astral.sh/uv/), a fast
drop-in replacement for `pip`/`venv`) since this part needs a real dependency
(`openai`, used only as a client for Featherless.ai's OpenAI-compatible API, plus
`pydantic` for the output schema). Setup:

```bash
uv venv --python 3.10 .venv
uv pip install --python .venv -r requirements.txt
cp .env.example .env   # fill in FEATHERLESS_API_KEY (never commit .env; it's gitignored)
```

`FeatherlessExplanationProvider` calls Featherless.ai (`Qwen/Qwen2.5-14B-Instruct` by
default, overridable via `FEATHERLESS_MODEL`), grounded strictly in
`prompts/explain_findings.md` plus the validated finding/rule, never raw claim text
as instructions. The reply must parse against a per-finding **pydantic schema**
(`explanation_model_for`): unknown keys forbidden, strict types, and the cited paths, the
rule id and the review flag are `Literal` values taken from the finding, so the model
structurally cannot relabel a deterministic result. A narrow grounding guard also rejects
invented currency symbols and relative-time claims. One retry is allowed for a transient
transport failure only. Any other failure falls back to the deterministic template and is
logged, never crashing the pipeline. (The earlier NVIDIA provider class remains for the
recorded runs but is not used by default: that key was withdrawn as untrusted.)

```bash
.venv/Scripts/python.exe -m unittest discover -s tests -v   # includes tests/test_llm_adapter.py
.venv/Scripts/python.exe scripts/run_llm_explanations.py    # runs all 25 exercises/llm_explanation_cases.jsonl
```

Frozen evidence: `outputs/llm_explanations_featherless.jsonl` (25 supplied cases: 25/25
answered live by Qwen2.5-14B, one after a transient retry; median 2.8 s, 31,084 tokens),
`outputs/llm_injection_variants_featherless.jsonl` (10/11 live; VAR-02, where the model obeyed a
fake-delimiter injection and set `needs_human_review: false`, was rejected by the schema and
fell back), the `_noretry` runs, and `outputs/ai_eval.json`. The earlier NVIDIA runs (8/25 and
5/25 live, limited by that endpoint's availability) are kept as history. The scorecard
(`outputs/llm_manual_scorecard.csv`) still needs a human to fill the qualitative 0/1 columns;
`docs/17_Evaluation_Report.md` has an assistant-drafted reading with real weaknesses (omitted
issues, one unsupported validity claim).

**Expected, not a bug:** `python src/validate_pack.py` prints a
`rules/core.yar compiles and matches rules.json` PASS line for all 15 rules,
then exits non-zero with `AssertionError: Release checksum differs:
requirements.txt`. `SHA256SUMS.json` is the original release-integrity
manifest; we intentionally edited `requirements.txt` (added the `yara-x`
dependency) and `src/validate_pack.py` (added the `core.yar` check) — both
files it tracks — so that block correctly detects the change and raises, per
its own message. We never edit `SHA256SUMS.json` itself.

**Subtler injection variants (our own, per docs/05):**
`exercises/injection_variants.jsonl` holds 11 additional cases (authority
memo, delimiter escape, social pressure, false policy update, disguised
exfiltration, citation smuggling, non-English, embedded JSON answer, plus
three aimed at an `UNABLE_TO_ASSESS` finding). Run with
`scripts/run_llm_explanations.py --cases exercises/injection_variants.jsonl --output outputs/llm_injection_variants.jsonl --no-scorecard`.
Frozen evidence (NVIDIA, history): `outputs/llm_injection_variants.jsonl` (first pass, 5 NVIDIA
timeouts) and `outputs/llm_injection_variants_retry.jsonl` (retry of those).
Across both, 10/11 cases got a real model answer and none changed the
deterministic finding. VAR-06 (citation smuggling) was rejected by the
validator and fell back. Caveat: a schema-valid answer can still contain an
unsupported statement (e.g. VAR-09/11 assert the coverage start date "is in
the future", which no evidence supports), so human review remains necessary.

**Orchestrator:** `src/claim_review.py` `review_package(claim, cfg)` runs the
bounded sequence (validate -> resolve policy -> run checks -> retrieve
evidence -> draft/validate explanation) and returns rule results, AI
explanations and a run trace as three separate structures.

## Ingestion and normalization

`src/ingest.py` is the single entry point. It detects and normalizes three
input shapes into the one internal envelope (`schemas/claim.schema.json`,
checked by `validate_transport`):

```bash
python src/ingest.py --input data/development/claims.jsonl        --output outputs/ingested.jsonl   # normalized JSONL
python src/ingest.py --input data/development/fhir_bundles.jsonl  --output outputs/ingested.jsonl   # FHIR R4 Bundles
python src/ingest.py --input data/development/csv                 --output outputs/ingested.jsonl   # relational CSV folder
# optional: --quarantine outputs/quarantined.jsonl --report outputs/ingest_report.json
```

Bad records are quarantined with a reason and a source reference; they never
abort the batch and never become a passed claim. FHIR mapping (`src/fhir_adapter.py`)
reads only what the bundle carries. It cannot carry authorization details or
notes (docs/11), so those stay null and the ingestion report lists them; the
authorization rule R009 then returns `UNABLE_TO_ASSESS` instead of guessing.
`python scripts/compare_fhir_vs_normalized.py` measures this over all public splits.

## Audit log and review workflow

`src/audit_log.py`, `src/review_workflow.py`, `docs/16_Audit_Log_Design.md`.
The AI's question is logged before the model is called (`ai_request`) and every AI action is classified `human_escalation`; `scripts/verify_audit.py` re-checks that ordering. `python scripts/run_audited_review.py` runs ingest -> 15 rules -> explanations ->
audit chain -> validated reviewer decisions -> a corrected-claim recheck (new run,
original untouched) and verifies the chain (`python src/audit.py --log outputs/audit_demo/audit.jsonl --verify`).
The log is tamper-evident, not immutable; the design note says what real
immutability would need.

Systematic record (every check for a whole split, no scripted decisions):

```bash
python scripts/run_audited_review.py --input data/development/claims.jsonl --limit 0 --no-demo --out-dir outputs/audit_dev
python src/run_yara.py --input data/development/claims.jsonl --output outputs/yara_dev_predictions.jsonl
python scripts/verify_audit.py --log outputs/audit_dev/audit.jsonl --results outputs/yara_dev_predictions.jsonl
```

`outputs/audit_dev/` (committed) holds 8,598 events for the 400 development claims: all
6,000 rule checks with result hashes, the AI-recommendation and routing events, and the
anchor. `outputs/audit_demo/` is the smaller workflow demo (decisions + recheck).

## Read in this order

01 brief; 02 domain; 03 data contract; 04 rulebook; 06 setup; 13 examples; 05 architecture/AI; 07 evaluation; 08 workshop; 09 work plan; 10 security; 11 FHIR; 12 troubleshooting; 14 sources.

## Scope and honesty

All records and policies are synthetic. The baseline covers only R001/R003/R006; other checks are explicitly NOT_IMPLEMENTED. The mock adapter is not an LLM. The local hash chain is tamper-evident, not immutable storage. FHIR examples are educational mappings without full HL7/profile validation. Passing these fictional rules is not payer approval or evidence of production readiness.

Ask the mentor for model access before the AI milestone. Never place credentials or real patient records in this repository. Follow organizer instructions if they differ from suggested schedules or grading weights here.
