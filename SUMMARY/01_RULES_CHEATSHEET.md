# The 15 Fictional Payer Rules — Cheat Sheet

Source of truth: `docs/04_Rulebook.md` + `rules/rules.json` + `rules/policies.json`.
All rule versions are `1.0.0`. Status precedence for every rule: **proven violation → FAIL**;
else **missing necessary evidence → UNABLE_TO_ASSESS**; else **PASS or NOT_APPLICABLE**.
Exactly one result per (claim, rule) → **15 results per claim, always**.

Implementation status in the starter code (`src/engine_core.py`): only R001, R003, R006 are implemented.
Everything else currently returns `NOT_IMPLEMENTED` and must be built.

| Rule | Severity | Status in starter | What it checks | FAILs when | UNABLE_TO_ASSESS when |
|---|---|---|---|---|---|
| **R001** Required claim information | high | ✅ implemented | invoice_number, member_id, diagnosis_code, and every line's service_date/service_code/quantity/unit_price/net_amount present & non-empty | any required field is known missing/empty | never (a known absence is always FAIL, not uncertain) |
| **R002** Service/submission chronology | high | ❌ TODO | every service_date ≤ submission_date | a service_date is after submission_date | dates missing/invalid and no other line proves violation |
| **R003** Coverage active on service date | high | ✅ implemented | coverage.status == active; service_date within [start_date, end_date] inclusive | known inactive status or date outside period | status/dates/service date unknown |
| **R004** Member/beneficiary consistency | high | ❌ TODO | patient_id == coverage.beneficiary_patient_id; member_id == coverage.member_id (case-sensitive) | known mismatch | comparison inputs missing |
| **R005** Provider in network | high | ❌ TODO | provider_id ∈ policy.allowed_providers | provider explicitly not listed | provider missing or policy unavailable |
| **R006** Possible duplicate lines | medium | ✅ implemented | repeated (service_code, service_date, modifier) in same claim; null modifier → "" | duplicate combo found | service_code/date missing and no other complete pair proves a dup |
| **R007** Line arithmetic | high | ❌ TODO | net_amount == quantity × unit_price (Decimal, ROUND_HALF_UP, ±0.01 SAR tolerance) | mismatch beyond tolerance | numeric input missing |
| **R008** Required authorization reference | high | ❌ TODO | for services in policy.auth_required_services, line.authorization_id non-empty | required and empty | unknown service code or policy unavailable |
| **R009** Authorization record matches | high | ❌ TODO | referenced authorization: matches patient_id + service_code, status approved, service_date within valid_from/valid_to, aggregate quantity per auth_id ≤ max_quantity | ID not found or known mismatch | R008 already failed on missing ID → UNABLE_TO_ASSESS here; or missing comparison input |
| **R010** Required supporting document | medium | ❌ TODO | policy.required_documents[service_code] type must have a matching attachment (type+patient_id+service_code+service_date) | absent or mismatched | matching attachment exists but is draft/unknown status (not "final") |
| **R011** Service code in catalogue | high | ❌ TODO | nonempty service_code ∈ rules/services.json | unknown code | service_code missing |
| **R012** Claim total equals line sum | high | ❌ TODO | total_amount == Σ line net_amount (ROUND_HALF_UP, ±0.01 SAR) | mismatch beyond tolerance | amount inputs missing |
| **R013** Quantity/price limits | medium | ❌ TODO | quantity positive integer ≤ policy.max_quantity_per_line[code]; 0 < unit_price ≤ policy.max_unit_price[code] | known violation | missing values, unknown code, or policy unavailable |
| **R014** Submission window | medium | ❌ TODO | submission_date − latest service_date ≤ policy.submission_window_days | window exceeded | dates/policy missing (negative lag = NOT_APPLICABLE, handled by R002 instead) |
| **R015** Currency matches policy | high | ❌ TODO | claim.currency == policy.currency (SAR) | known mismatch | currency or policy missing |

## Policy profiles (rules/policies.json)

| Parameter | EDU-BASIC | EDU-PLUS |
|---|---|---|
| Submission window | 30 days | 60 days |
| Currency | SAR | SAR |
| Allowed network | EDU-PROV-01/02/03 | same |
| Authorization required for | SVC-IMAGE, SVC-THERAPY | same |
| Required documents | SVC-IMAGE→imaging-report; SVC-DENTAL→service-note | same |

## Service catalogue limits (same for both policies)

| Service | Max unit price (SAR) | Max qty/line |
|---|---|---|
| SVC-CONSULT | 350 | 1 |
| SVC-LAB | 260 | 3 |
| SVC-IMAGE | 2200 | 1 |
| SVC-THERAPY | 450 | 4 |
| SVC-DENTAL | 800 | 2 |
| SVC-PHARM | 200 | 10 |

## Cross-cutting conventions (apply to every rule)

- Dates compared at **day precision**, ISO format, **boundaries inclusive**.
- Money: **Decimal arithmetic + ROUND_HALF_UP**, never binary float comparison; 0.01 SAR tolerance is inclusive.
- Identifiers are **case-sensitive exact match** — never trim/normalize source data.
- Empty `authorizations`/`attachments` arrays = "known empty inventory", not missing data.
- `null` comparison value = unknown. Unrecognized `policy_id` = "no policy supplied", not proof of non-coverage.
- Evidence = JSON pointer into the **original normalized claim** + exact observed value (never a label file).
- A missing required field is itself an R001 defect; dependent rules must not invent the missing value (they typically return UNABLE_TO_ASSESS instead).
- Multiple findings across rules are intentional and not mutually exclusive.
- Deterministic checks: `confidence: null`, `confidence_kind: "not_probabilistic"`.
