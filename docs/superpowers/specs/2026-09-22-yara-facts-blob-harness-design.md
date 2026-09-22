# YARA facts-blob harness for R001/R003/R006 — design

Date: 2026-09-22
Status: approved
Scope: first slice of the ClaimGuard Engine Spec (Sep 22, 2026), build-order steps 1–2 only.

## Purpose

The full ClaimGuard Engine Spec (pasted 2026-09-22) covers ~10 largely
independent subsystems: the YARA rules engine (R001–R015 + extension
pack), the NVIDIA-backed LLM explanation adapter, the RAG retrieval
seam, JSONL/CSV/FHIR ingestion, six CLI tools + a REST API, the review
queue and recheck flow, the audit hash chain + admin terminal, PDF/photo
document intake, workflow verification, the AI companion, the symptom
checker, and Google/passkey auth — each with its own security
hardening requirements.

That is too large for one design or one implementation plan. This
document scopes only the foundation everything else plugs into: prove
that a deterministic Python fact extractor + a compiled YARA rule pack
can reproduce the existing three-rule baseline (`engine_core.baseline`
for R001/R003/R006) exactly, before extending the pattern to the
remaining twelve rules. Later slices (R002/R004/R005, then R007/R012/
R015, etc., per the spec's own 12-step build order) get their own
brainstorming pass once this one lands.

## Non-negotiables carried into this slice

From Section 1 of the engine spec, the ones this slice can actually
violate if built carelessly:

- Never show `NOT_IMPLEMENTED` as `PASS`.
- Never invent data — a missing field is `UNABLE_TO_ASSESS` or `FAIL`,
  never guessed.
- Deterministic checks always report `confidence: null,
  confidence_kind: not_probabilistic`.
- A rule that produces no outcome fails loudly (`EngineError`), never
  silently defaults to a pass.

## What already exists (starter pack, untouched by this slice)

- `src/engine_core.py` — `base_check()` implements R001/R003/R006
  directly in Python; `baseline()` runs all 15 `rules.json` entries,
  marking the other twelve `NOT_IMPLEMENTED`.
- `rules/rules.json` — the 15 rules' authoritative logic descriptions,
  `rule_version`, `severity`, `corrective_action`, `source`.
- `schemas/result.schema.json` — the result record contract every
  pipeline (old and new) must satisfy.
- `tests/test_baseline.py` — exercises `engine_core.base_check`
  directly; not modified by this slice.

Nothing in `engine_core.py`, `run_baseline.py`, `rules/rules.json`, or
the existing tests changes. The new pipeline is additive and proven
against the old one, not a replacement of it (yet).

## New components

**`src/facts_extractor.py`** — pure, standard-library-only functions,
one per rule: `r001_details(claim) -> dict`, `r003_details(claim) ->
dict`, `r006_details(claim) -> dict`. Each mirrors the logic already in
`engine_core.base_check` for that rule, but computes it once and
returns everything derived from it — `facts` (the tagged fact lines
below), `evidence_paths`, `line_ids`, and `message` — in a single pass,
so the tags YARA sees and the fields assembled into the final result
can never drift apart from each other:

```
R001:MISSING:<path>            (one per missing field)
R001:OK

R003:INACTIVE:status=<s>
R003:OUT_OF_PERIOD:<path>:service=<d>:start=<d>:end=<d>
R003:UNKNOWN
R003:OK

R006:DUPLICATE:<lineA>,<lineB>:key=<code>|<date>|<mod>
R006:UNKNOWN
R006:OK
```

A `build_blob(claim) -> str` function joins the three `details['facts']`
lists into the flat, line-oriented blob, generated fresh on every run.

**`rules/core.yar`** — one YARA rule per (rule_id, outcome) pair, for
R001/R003/R006 only, following the Section 3 skeleton exactly (`meta:
rule_id`, `outcome`, `severity`, `rule_version`). `rule_version` values
match `rules/rules.json`'s `"1.0.0"` for these three rules.

**`src/yara_engine.py`**:
- Compiles `rules/core.yar` once (module-level cache), computes and
  exposes its content hash (`hashlib.sha256`) for future audit-trail
  use — not consumed by anything yet in this slice.
- `build_blob(claim)` → scan via `yara_x` → group `matching_rules` by
  `meta["rule_id"]` into a set of matched outcomes per rule.
- Resolve precedence with the fixed list `["FAIL",
  "UNABLE_TO_ASSESS", "NOT_APPLICABLE", "PASS"]`, exactly as Section 3
  specifies, including raising `EngineError` when a rule in scope
  produces no outcome at all.
- Assemble a result dict matching `schemas/result.schema.json` for
  each of R001/R003/R006, using each rule's `details['evidence_paths']`,
  `['line_ids']` and `['message']` from the *same* `rXXX_details()` call
  that produced the fact tags YARA just matched — never a second,
  independently-derived computation.

**Evidence assembly rule** (the one judgment call in this slice):
`schemas/result.schema.json`'s `evidence` array pairs a JSON pointer
path with the value `pointer()` finds there on the actual claim —
exactly how `engine_core.make_result` already builds it today. Some of
those paths come straight from a fact tag YARA matched (e.g. R001's
per-field `MISSING:<path>` tags); others are a fixed, rule-specific set
the current baseline also always reports regardless of outcome (e.g.
R003 always evidences `/coverage/status`, `/coverage/start_date`,
`/coverage/end_date` and every line's `service_date`, whether or not
that line is the one that failed). Either way, the *path* is something
the extractor genuinely identified as relevant — never guessed — and
the *value* at that path is a direct, unaltered read of the input, not
a computation. That satisfies "never invent data": nothing about a
violation is invented, and nothing about a value is fabricated after
the fact — it is read once, from the claim, at a path the same
deterministic pass through the claim already decided mattered.

**`tests/test_facts_blob.py`** — hand-built facts-blob fixtures per
Section 11 of the engine spec: one PASS, one FAIL, one
UNABLE_TO_ASSESS per rule (none of R001/R003/R006 has a
`NOT_APPLICABLE` outcome). These compile `rules/core.yar` directly and
scan hand-written tag strings — bypassing both `facts_extractor.py` and
`yara_engine.py` entirely — so a broken YARA pattern is caught at its
source, independent of extractor or precedence-resolution correctness.

**`requirements.txt`** gains one pinned line: `yara-x==1.20.0`
(confirmed available on PyPI at spec-writing time). This is the first
dependency added to what was previously a zero-dependency starter
pack — the engine spec's Section 8 explicitly permits this ("the
baseline's zero-dependency constraint no longer holds once yara-x and
an HTTP client are added").

## Proof of equivalence

A throwaway script, `scripts/diff_baseline_vs_yara.py` (not a
deliverable, not committed as project output — a one-time check),
runs both `engine_core.baseline()` and the new `yara_engine` pipeline
over every claim in `data/development/claims.jsonl`, restricted to
R001/R003/R006, and asserts field-for-field equality of every result.
This is the literal instantiation of the engine spec's build-order
step 2: "prove the new architecture reproduces the existing baseline
exactly before extending it."

## Out of scope (deferred to later slices)

R002/R004/R005 and all remaining rules; the extension pack (X001–
X003); the LLM explanation adapter and `PolicyRetriever`/RAG seam;
JSONL/CSV/FHIR ingestion beyond what `engine_core` already validates;
the six CLI tools and REST API; the review queue and recheck flow; the
audit hash chain and admin terminal; PDF/photo document intake;
workflow verification; the AI companion; the symptom checker; Google/
passkey auth; and Section 22's security hardening. Each gets its own
brainstorming pass before implementation, per the engine spec's own
12-step build order.

## Testing

- `tests/test_facts_blob.py` — YARA layer against hand-built fixtures,
  per rule, per outcome (PASS/FAIL/UNABLE_TO_ASSESS), as required by
  Section 11.
- `scripts/diff_baseline_vs_yara.py` — end-to-end equivalence proof
  against the full development split (400 claims).
- `src/validate_pack.py` extended, additively, to also compile
  `rules/core.yar` and confirm every rule_id/version it defines
  matches `rules/rules.json` — scoped to the rule ids actually present
  in the pack so it doesn't fail on R002–R015, which aren't in
  `core.yar` yet.
- Existing `tests/test_baseline.py` is untouched and must keep
  passing unmodified — it's the ground truth this slice is proving
  against.
