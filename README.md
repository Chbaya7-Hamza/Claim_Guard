# ClaimGuard AI

A pre-validation copilot for **synthetic** healthcare claims. It ingests claims (FHIR R4 JSON, CSV or JSONL), checks them against a fictional payer rulebook of 15 rules with a deterministic engine, explains each finding with a tightly bounded AI step, and records every check, AI action and human decision in a tamper-evident audit log. A human always makes the final call.

Built for the CSTAM-VELODOC challenge (mentor: Dr. Wael Hilali). All data, codes, prices and payer rules are invented. Nothing here is a real reimbursement system.

> **New to the project? Read [TEAM.md](TEAM.md)** for what we built, why each decision was made, and what the experiments showed.

## How it works

```
 FHIR / CSV / JSONL ──► ingestion ──► facts extractor ──► YARA-X rule pack ──► 15 structured results
   (bad records are        │            (one function        (declarative        (schema-checked,
    quarantined)           │             per rule)            outcome rules)      never a silent pass)
                           ▼                                                            │
                     audit log  ◄──────────── every check, AI question, AI answer ◄─────┤
                (hash chain + anchor)                                                   ▼
                           ▲                                              bounded AI explanation
                           │                                            (schema + grounding checks,
                     human review  ◄────────────── findings ◄───────────  template fallback)
              (confirm / dismiss with reason /
               request info / corrected → recheck as a new run)
```

Three rules of the design: the **engine decides and the AI only explains**; **unknown is never a pass** (missing data gives `UNABLE_TO_ASSESS`); and the **original input is never changed**, a correction is rechecked as a new version.

## Phase 1 deliverables and where each lives

| Rubric item | Where it is | Verify |
|---|---|---|
| **Data ingestion and normalization** (FHIR R4 JSON / CSV to one internal form) | `src/ingest.py` (format detection, quarantine), `src/fhir_adapter.py`, `src/csv_to_jsonl.py`; envelope `schemas/claim.schema.json` | `python src/ingest.py --input data/development/fhir_bundles.jsonl --output outputs/ingest_normalized.jsonl --report outputs/ingest_report.json` |
| **Deterministic and AI rule engine** (15 fictional rules) | `rules/core.yar` + `rules/rules.json`, `src/yara_engine.py`; bounded AI in `src/llm_adapter.py` | `python src/run_yara.py` ; metrics in `outputs/yara_*_metrics.json` |
| **Explainability and structured output** | `schemas/result.schema.json`; every result is validated against it | `python -m unittest tests.test_phase1_rubric` |
| **Audit log engine** | `src/audit_log.py`, design in `docs/16_Audit_Log_Design.md` | `python scripts/verify_audit.py --log outputs/audit_dev/audit.jsonl `  (chain + AI ordering; add `--results` after `run_yara.py` to also cross-check every result hash) |

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

**Audit log.** It records ingestion, every rule check with its confidence fields, the AI's question (written before the model is called), the AI recommendation, and system and human decisions, as a hash chain plus a separately stored head-hash anchor. This is tamper-*evident*, not immutable: `docs/16_Audit_Log_Design.md` states what production immutability would additionally need (write-once storage, an externally held anchor, authenticated reviewers). Setting `AUDIT_ANCHOR_KEY` signs the anchor so it cannot be forged without the key (`docs/20_Security_Audit.md`).

## Quick start

Python 3.10 or newer (tested on 3.10, 3.12 and 3.14). The rule engine needs `yara-x`; the AI step needs `openai` and `pydantic`. Everything else is the standard library.

```bash
uv venv --python 3.10 .venv
uv pip install --python .venv -r requirements.txt
cp .env.example .env        # optional: add FEATHERLESS_API_KEY for live AI explanations. Never commit .env.

python -m unittest discover -s tests          # 364 tests, about 60 s, offline, no API key needed

# run the 15 rules over a split, score it against the answer key, and open the review page
python src/run_yara.py --input data/development/claims.jsonl --output outputs/yara_dev_predictions.jsonl
python src/evaluate.py --gold data/development/expected_results.jsonl --pred outputs/yara_dev_predictions.jsonl \
    --claims data/development/claims.jsonl --output outputs/yara_dev_metrics.json
python src/make_review.py --input outputs/yara_dev_predictions.jsonl --output outputs/yara_review.html

# a full audited review (ingest -> rules -> AI explanation -> audit -> reviewer decisions -> recheck)
python scripts/run_audited_review.py
python scripts/verify_audit.py --log outputs/audit_demo/audit.jsonl   # run_audited_review.py rewrites the committed outputs/audit_demo sample with fresh ids and timestamps
```

On Windows use `.venv\Scripts\python.exe`. Without an API key the AI step uses a deterministic template, so every command above works offline.

## Results

| Measure | Result |
|---|---|
| Status accuracy, issue precision and recall, all 15 rules | **1.0** on the development, validation and stress splits (9,000 of 9,000 results) |
| Independent oracle agreement (rules written again from the rulebook text alone) | 0 disagreements over about 111,000 generated claims and 123 hand-derived edge cases |
| Tests | 364, all offline, on Python 3.10, 3.12 and 3.14 (last verified on all three at the commit named in `docs/19`) |
| Live AI explanations (Qwen2.5-14B via Featherless.ai) | see `docs/21_Experiments.md` for temperature, model and prompt experiments |
| Security | audited against the OWASP Top 10 for LLM Applications and the OWASP Top 10: `docs/20_Security_Audit.md` |

Perfect scores on the public splits are not evidence of generalization. The mentor-held 200 claims are not available to us; the independent oracle and the stress tests are the closest substitute.

## Repository map

| Path | What is in it |
|---|---|
| `src/` | The system: `ingest.py`, `fhir_adapter.py`, `csv_to_jsonl.py` (ingestion); `facts_extractor.py`, `yara_engine.py` (rules); `llm_adapter.py`, `claim_review.py` (bounded AI); `audit_log.py`, `review_workflow.py` (audit and review); `advisory.py` (checks outside the 15 rules); `make_review.py` (offline review page) |
| `rules/` | `core.yar` (compiled rule pack), `rules.json`, `policies.json`, catalogues |
| `schemas/` | JSON schemas for claims, results and review events |
| `data/` | 600 synthetic claims in three splits, in JSONL, CSV and FHIR forms, with the public answer key |
| `tests/` | 364 tests, including `oracle.py` (independent reference implementation) and the stress and security suites |
| `scripts/` | Audited runs, audit verification, AI evaluation and the experiment runner |
| `experiments/` | Raw experiment data and `summary.json`; figures are in `docs/figures/` |
| `outputs/` | Frozen evidence: metrics, audit samples, recorded live AI runs |
| `docs/` | Numbered documents; see the index below |
| `prompts/`, `exercises/` | The AI prompt (v1.3.0) and its variants; the 25 supplied and our own test cases |

## Documents

| Read | For |
|---|---|
| [TEAM.md](TEAM.md) | What we built and why; onboarding for teammates |
| `docs/04_Rulebook.md` | The 15 fictional rules |
| `docs/16_Audit_Log_Design.md` | Audit log design and what real immutability would need |
| `docs/17_Evaluation_Report.md` | Metrics, error analysis, AI evaluation, limitations |
| `docs/19_Stress_Testing_and_Judging_Coverage.md` | How the rules were stress-tested; each judged item mapped to its test |
| `docs/20_Security_Audit.md` | OWASP audit, red-team run, fixes, residual risks |
| `docs/21_Experiments.md` | AI experiments: temperature, model, prompt, concurrency |
| `docs/00_Starter_Pack_README.md` | The organizers' original starter-pack README, kept in full |

## Boundaries

No clinical judgement, medical-necessity decision, fraud accusation, automatic approval, live payer submission or EHR integration. A PASS means "these 15 checks passed on the supplied data", never that a claim is valid or payable. Reviewer identity is self-declared: there is no authentication yet.

**`python src/validate_pack.py` exits non-zero on purpose.** It prints a PASS line for the rule pack, then stops with `Release checksum differs`, because the organizers' `SHA256SUMS.json` correctly detects our intentional edits to files it tracks. We never edit `SHA256SUMS.json` itself.

## Status

Phase 1 (ingestion, rule engine, structured output, audit log) is complete. Not yet built: the review interface as a mobile app on a local API server, authentication, the architecture diagram, demo video and pitch.
