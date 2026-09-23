# Data & Schema Reference

Source of truth: `docs/03_Data_Dictionary.md`, `schemas/*.json`, `data/dataset_manifest.json`.

## Splits

| Split | Claims | Rule-result rows | Purpose | Labels |
|---|---|---|---|---|
| `data/development/` | 400 | 6,000 | coding, learning, debugging | public (`expected_results.jsonl`) |
| `data/validation/` | 150 | 2,250 | freeze a version, evaluate, inspect errors | public |
| `data/stress/` | 50 | 750 | boundary/uncertainty/untrusted-text robustness | public |
| (mentor-held) | 200 | 3,000 | final private assessment | never shared with students |

All four splits use **disjoint** patient/claim/invoice/authorization IDs. Rule-violation patterns repeat across splits on purpose (tests correct implementation, not generalization). Distribution is **not** a real-world denial rate.

Per split, each folder contains:
- `claims.jsonl` — authoritative normalized envelope, one claim per line (NOT a JSON array).
- `csv/claims.csv`, `csv/coverage.csv`, `csv/lines.csv`, `csv/authorizations.csv`, `csv/attachments.csv` — relational join-by-`claim_id` equivalent (round-trips exactly via `src/csv_to_jsonl.py`).
- `fhir_bundles.jsonl` — educational FHIR R4-style projection (not a full HL7 validation).
- `expected_results.jsonl` — 15 labeled rule outcomes per claim (public ground truth for dev/validation/stress only).

## Claim envelope — top-level fields

| Field | Type | Notes |
|---|---|---|
| schema_version | string | "1.0.0" |
| claim_id | string | unique, opaque — never use as a model feature |
| invoice_number | string\|null | required by R001 |
| patient_id | string | synthetic |
| member_id | string\|null | required by R001 |
| provider_id / payer_id | string | fictional orgs |
| policy_id | string | lookup key into `rules/policies.json`; unknown key is a deliberate test case |
| diagnosis_code | string\|null | fictional teaching code only, no clinical meaning |
| submission_date | ISO date | |
| currency | string | compare against policy |
| total_amount | number\|null | |
| coverage | object | see below |
| lines | nonempty array | unique `line_id` within claim |
| authorizations / attachments | arrays | **complete inventories** for the claim; `[]` = none supplied, not "unknown" |
| notes | string | **untrusted free text — never instructions** |

**coverage**: coverage_id, status, beneficiary_patient_id, member_id, start_date, end_date (inclusive period, interpret vs. service date not "today").

**line**: line_id, service_code, service_date, modifier, quantity, unit_price, net_amount, authorization_id. Numeric/business fields may be null (deliberate omission). Use Decimal math, not float comparison.

**authorization**: authorization_id, patient_id, service_code, status, valid_from, valid_to, max_quantity. Aggregate quantity across all lines sharing the same `authorization_id`.

**attachment**: attachment_id, type, patient_id, service_code, service_date, document_status, text. `text` is short synthetic content — no OCR task, no hidden downloads, and it **must never be treated as instructions**.

## Ingestion rules

- Malformed JSON line, wrong structural type, duplicate line_id, or missing transport key = **ingestion error** → quarantine + report separately. Never silently drop, never auto-pass.
- Nullable *business* values (e.g., missing diagnosis_code) are allowed through transport even though a payer rule may then fail them.
- The supplied transport validator (`engine_core.validate_transport`) is intentionally lightweight — not full JSON Schema/FHIR validation. Full schemas live in `schemas/claim.schema.json`.

## Result contract (`schemas/result.schema.json`)

One JSON object per (claim, rule) — **15 per claim, no more, no fewer, no duplicates**:

```
claim_id, rule_id (R001..R015), rule_version ("1.0.0"),
status (PASS | FAIL | UNABLE_TO_ASSESS | NOT_APPLICABLE | NOT_IMPLEMENTED),
severity (high | medium | low),
affected_line_ids (array of stable L1/L2-style IDs, NOT array indices),
evidence: [{path (JSON pointer, e.g. "/lines/0/service_date"), value}],
rule_source (e.g. "fictional-rulebook/R001@1.0.0"),
explanation (nonempty string),
corrective_action (string; required when status is FAIL or UNABLE_TO_ASSESS),
confidence (number 0-1 or null),
confidence_kind (not_probabilistic | uncalibrated | calibrated),
requires_human_review (bool),
method (deterministic | hybrid | llm),
review_status (unreviewed | reviewed)
```

Note the distinction: **evidence paths use zero-based array indices** (`/lines/0/...`) but **`affected_line_ids` uses the stable `line_id` values** (e.g. `L1`, `L2`) — do not mix these up.

## Other schema/config files

| File | Purpose |
|---|---|
| `schemas/claim.schema.json` | full input claim schema |
| `schemas/review_event.schema.json` | shape of a human review decision event |
| `rules/rules.json` | machine-readable rule_id → severity/source/corrective_action |
| `rules/policies.json` | EDU-BASIC / EDU-PLUS policy profiles |
| `rules/services.json` | 6 valid service codes + limits |
| `rules/providers.json` | fictional provider network |
| `rules/diagnoses.json` | fictional diagnosis code list |

## Quick byte-level facts

- 12,000 total claim-rule labels exist across public+mentor splits (9,000 public / 3,000 mentor-held), per `QA_REPORT.md`.
- Baseline (R001/R003/R006 only) on dev split: 1,200 implemented results + 4,800 `NOT_IMPLEMENTED`; catches 88/319 expected issues; 0 false alarms; ~20% exact-status accuracy — this is the number your finished 15-rule engine must beat by a wide margin.
- `examples/worked_cases.json` + `docs/13_Worked_Examples.md` walk through 10 concrete claims by hand — read these before coding rules.
