# TEAM.md: what we built, and on what grounds

For everyone on the team, including anyone who joins later. The [README](README.md) says how to run things. This file says **what the system is, why it is shaped this way, how we know it works, and where it is weak.** Where a claim rests on evidence, the evidence is named so you can check it.

## 1. The system in one page

**The problem.** Insurance claims are often rejected because of avoidable defects: a missing field, dates in the wrong order, a total that does not add up, an expired authorization. A reviewer wants those found before submission, with the reason and the evidence, and wants to stay in control.

**What we built.** A pipeline for **synthetic** claims and a **fictional** payer rulebook (15 rules):

1. **Ingest** claims from FHIR R4 bundles, CSV folders or JSONL into one internal format. A bad record is quarantined with a reason; it never stops the batch and never becomes a "pass".
2. **Check** each claim against the 15 rules with a deterministic engine. Every result has a Claim ID, Rule ID and version, severity, the evidence (a pointer into the claim plus the observed value), an explanation and a corrective action.
3. **Explain** each FAIL or UNABLE_TO_ASSESS finding in plain language with a small language model that can only *explain*: it cannot change a verdict, and any reply that breaks the schema or invents facts is thrown away and replaced by a fixed template.
4. **Review.** A human confirms, dismisses (with a reason), requests information or marks a correction. A corrected claim is rechecked as a **new run**; the original is never edited.
5. **Record.** Every check, AI question, AI answer, system decision and human decision goes into a hash-chained audit log. The AI's question is written *before* the model is called.

**Three rules everything else follows from:**

| Rule | Why |
|---|---|
| The engine decides; the AI only explains | The rubric's non-negotiable checks say a model failure must not remove a finding. A verdict must be reproducible and explainable line by line; a language model cannot promise that. |
| Unknown is never a pass | Missing or unusable data gives `UNABLE_TO_ASSESS`. A green result on data we could not check is the most damaging thing this system could do. |
| The original input is never changed | An auditor must be able to see exactly what was submitted and what was decided about it. |

**What it is not.** Not a real reimbursement system: no clinical judgement, no medical-necessity decision, no fraud accusation, no automatic approval, no payer submission. A PASS means "these 15 checks passed on the supplied data", nothing more.

## 2. The team and how we worked

The repository does not record who the team members are or who did what, so **nothing is invented here.** Fill this in (and `docs/18_Contribution_Log.md`, which the challenge requires):

| Team member | Role | What they did | Evidence (commits, reviews) |
|---|---|---|---|
| _to fill in_ | _to fill in_ | _to fill in_ | _to fill in_ |
| _to fill in_ | _to fill in_ | _to fill in_ | _to fill in_ |

**AI coding tools.** The code was written with Claude Code (Anthropic) under the team lead's direction, 2026-09-21 to 2026-09-26. The team lead chose the architecture (a compiled YARA-X rule pack fed by a fact extractor), supplied the four graded Phase 1 deliverables, chose the model provider, and decided what to prioritize (Phase 1 first, then stress testing, security, experiments; the mobile app and local API are a later phase). A separate reviewer model was consulted before large design choices. The full account is in `docs/18_Contribution_Log.md`.

**Be clear-eyed about one thing:** the checks on that AI-written code are mostly automated (tests, an independent oracle, the organizers' answer key, red-team runs). A human reading of the code is **not recorded anywhere** in the repository. Someone on the team should review the modules and write down what they reviewed.

## 3. What is in the box

| Part | Files | Job | Why it exists |
|---|---|---|---|
| Ingestion | `src/ingest.py`, `fhir_adapter.py`, `csv_to_jsonl.py`, `jsonl_reader.py` | Turn three input shapes into one claim format; quarantine bad records | Rubric item 1. The FHIR route reads only what a bundle carries and leaves the rest unknown instead of guessing |
| Fact extractor | `src/facts_extractor.py` | One function per rule: reads the claim, returns facts, evidence paths, affected lines and a message | One place computes what a rule saw, so the rule pack and the result text cannot drift apart |
| Rule pack | `rules/core.yar` (YARA-X) | Declarative outcome rules: FAIL, UNABLE, NOT_APPLICABLE or PASS from the facts | The team lead's architecture choice; the outcome logic is data you can read, separate from the code that gathers facts |
| Engine | `src/yara_engine.py` | Compile, scan, resolve precedence (FAIL over UNABLE over NOT_APPLICABLE over PASS), assemble results, isolate a crashing rule | A rule that crashes becomes UNABLE for that rule only; a rule with no outcome stops the run loudly |
| Bounded AI | `src/llm_adapter.py`, `claim_review.py`, `prompts/` (v1.3.0 and experiment variants) | Explain findings with a model; validate every reply; fall back to a template | Rubric item 2 (AI half) and the grounding requirement |
| Audit log | `src/audit_log.py`, `audit.py` | Hash chain, separate anchor, write-ahead AI records, duplicate-submission and advisory events | Rubric item 4 |
| Review workflow | `src/review_workflow.py`, `make_review.py` | Validated decisions, unresolved counts, recheck as a new run, offline review page | MVP items 4 and 5 |
| Advisories | `src/advisory.py` | Flag defects none of the 15 rules cover (unknown diagnosis code, payer mismatch) | Found by red-teaming; kept outside the scored rules on purpose |
| Verification | `tests/` (see the README for the count), `tests/oracle.py`, `scripts/` | Prove and re-prove all of the above | See section 5 |

## 4. Decisions and their grounds

| Decision | Grounds | Trade-off or caveat |
|---|---|---|
| Deterministic engine, AI explains only | Rubric non-negotiables; a verdict must be reproducible | Explanations can be plain but shallow; a model cannot find defects the rules do not define |
| Fact extractor plus a compiled YARA-X pack | The team lead's architecture. First proven equal to the organizers' three-rule baseline, then extended one rule at a time (`docs/superpowers/specs/`) | The pack matches text by substring. A claim value like `USD R009:MISMATCH:` once forged a finding on another rule; fixed by encoding all claim data before it enters a fact (`docs/20`, finding F1) |
| Precedence: a proven violation beats a missing input | `docs/04` shared conventions | Found missing in R009 and R013 by the independent oracle; fixed |
| `confidence` is null for rule results | `docs/04` says deterministic checks carry `confidence: null`; the organizers' answer key does the same on all 6,000 development results | A grader who expects a number will ask. An invented score would pretend to be a probability |
| Missing or invalid data is `UNABLE_TO_ASSESS`, never a guess | `docs/04`; the FHIR route cannot carry authorizations, so R009 is UNABLE there (310 of 600 claims) | More work for reviewers; correct by construction |
| Fail closed everywhere | A claim that breaks the input contract still gets 15 UNABLE results; a rule that crashes becomes UNABLE; a model failure falls back to the template | A run that "succeeds" with warnings must be read, not ignored (`run_yara` exits with code 2 then) |
| Trust boundary for the AI in the orchestrator | A red-team style test showed a pluggable provider could edit the finding it explained (a FAIL became a PASS) and could return unchecked replies. Now every reply is validated and providers get copies | Double validation for the built-in provider; cheap |
| Featherless.ai, open-weight `Qwen/Qwen2.5-14B-Instruct` | The first provider's key was withdrawn as untrusted; an open-weight model behind an OpenAI-compatible API keeps us swappable | Synthetic data only. With real patient data this sends PHI to a third party; needs a data-processing agreement or an on-premise model (`docs/20`, LLM02) |
| Hash-chained audit log with a separate anchor | Tamper evidence for edits, deletions and truncation; the AI question is logged before the call | Whoever can write the files can rewrite chain and anchor together. `AUDIT_ANCHOR_KEY` signs the anchor to prevent that; the default is unkeyed. Not immutable storage |
| Ingestion quarantines instead of aborting | A held-out file may hold anything (BOM, bad bytes, giant numbers, a U+2028 in a value) | Every quarantined record must be counted and explained (it is) |
| Test against an independent oracle, not only the answer key | A 100% score on 600 public claims cannot show correctness on unseen data | The oracle was written by the same team from the same text; a shared misreading would survive (`docs/19` section 4) |
| Advisories are separate from the 15 rules | The rulebook fixes the scored set, so a new rule would change scored output | They only route a claim to a human; they never change a status |

## 5. How we know it works

Six layers of checking, from cheap to demanding. Each layer found real defects that the earlier ones missed.

| Layer | What it shows | Result |
|---|---|---|
| The organizers' answer key | Every rule agrees with the supplied labels | 9,000 of 9,000 results on development, validation and stress; precision, recall and status accuracy 1.0 |
| Worked examples | The handbook's own ten cases | Exact match |
| Independent oracle | A second implementation of the 15 rules from the rulebook text alone (`tests/oracle.py`) agrees with the engine | 0 disagreements over about 111,000 generated claims and 123 hand-derived boundary cases. It first found precedence bugs in R009 and R013, an exact-versus-rounded amount question, and a Python-version-dependent date parse |
| Hostile inputs at every entry | Files, bundles, CSV, the review page, the audit log | Found: a BOM losing the first claim, a 4,300-digit integer aborting a run, a U+2028 breaking an audit log, malformed FHIR aborting ingestion |
| Security audit | OWASP Top 10 for LLM Applications and the OWASP Top 10 | Found: claim data forging findings through the rule facts; unbounded prompts; log forging; a forgeable audit anchor (`docs/20`) |
| Red team | 30+ attacks through the real audited pipeline | No claim that broke a rule got through unflagged. Found: replays went unnoticed; defects outside the 15 rules passed cleanly. Both fixed |

The lesson: **a passing score is a claim, not a proof.** Every layer above the answer key existed because the layer below could not see a whole class of failure.

## 6. Experiments: can we make the AI step better?

The rules score 1.0 and have nothing to tune, so the only optimizable part is the explanation step: which model, what temperature, what instruction text, how many parallel calls. We wrote the metrics and the decision rule **before** running anything (`docs/21_Experiments.md`), ran everything through the production path, and checked that no setting ever changed a verdict.

We ran six experiments (2,136 live calls, 2026-09-26) on the Featherless.ai endpoint. The main findings:

| Question | Answer | Evidence |
|---|---|---|
| Does any setting change a verdict? | **No.** The finding was hashed before and after each of 2,136 calls; identical everywhere | `experiments/summary.json` |
| Which temperature? | **0.** Best on every quality measure; live answers fall from 93% to 78 to 82% at 0.5 to 1.0 and garbled replies rise from 10% to 32% | E1, ![E1](docs/figures/e1_useful_vs_temperature.png) |
| Is temperature 0 deterministic? | **No.** On the hosted 14B model only 1 of 30 cases repeated word for word; the wording still varies | E1 |
| Which model? | Depends on what you value. The 7B model never garbles and is fastest (1.9 s), Mistral-Nemo never garbles and is fluent, the 14B default is fluent but garbles about a fifth of its raw replies at temperature 0, the 32B model is worst | E2, ![reliability](docs/figures/reliability_degenerate_replies.png) |
| Which prompt? | A worked example makes a small model write fuller explanations (names a next step in 92% of answers) but lowers its injection resistance to 88.9%; a short prompt makes it copy the template | E3 |
| How many parallel calls? | 8. Throughput rises from 29 to 207 calls per minute with no rate limiting | E4 |
| Should we switch the default? | **No, and this overrides the pre-registered rule, so read it as a judgement.** The rule selected 7B with the short prompt (100% useful). We declined to recommend it because its answers restate the engine's own sentence and never cite an evidence value, added a follow-up experiment, and no fluent candidate passed that either. The default stays as the status quo, not because it passed: it fails the follow-up's first test (garbled replies) | E5, E6 |

What the experiments changed in the product: the garbled-output guard. Three garbled explanations (valid JSON, correct citations) passed the schema and grounding checks and were shown as normal live answers. `check_grounding` now rejects text in another script, a replacement character, and long repetitions, tested against about 1,500 recorded answers.

**How to read these results honestly.** The primary metric ("useful") is a mechanical check that rewards echoing the template and that flags harmless paraphrases; we kept it as pre-registered, reported a lenient version beside it, and added measures for whether an answer adds anything. A hosted endpoint drifts over time (the same configuration scored 78.7%, 76.9% and 59.8% in three runs), so only the interleaved experiments (E5, E6) compare configurations fairly. Nobody has scored these answers by hand yet, and that is the evidence that would settle model choice. Everything, including the threats to validity and the deviations from the plan, is in `docs/21_Experiments.md`; raw replies are in `experiments/raw/`.

## 7. What we got wrong, and what to remember

- **We trusted the score.** Perfect public scores hid two precedence bugs and a rounding ambiguity until an independent oracle looked.
- **We checked statuses, not content.** The accuracy gate cannot see a change to a result's evidence. A fix to R009 silently changed three results' hashes; only the audit cross-check noticed. There is now a test that pins every logged result hash.
- **Our safety net had a hole we only saw by measuring.** Garbled model output (valid JSON, gibberish text) passed both checks until the experiments counted it. A guard is only as good as the failures you have looked for.
- **We put a safety check inside one class.** The schema and grounding checks lived in the built-in provider, so any other provider bypassed them. Safety checks belong in the orchestrator.
- **We let a metric flatter or punish without checking it.** The pre-registered "omitted reason" check flags paraphrases (most of the 30 flagged answers we read were fine), and it rewards near-copies of the template. We kept the original number and reported a lenient one beside it.
- **Small habits that mattered:** exact version pins, no `subprocess` or `eval` in our code (a test scans for it), `%r` in log calls, ASCII-escaped JSONL rows.

## 8. Known limits and what comes next

| Limit | Status |
|---|---|
| No authentication; reviewer identity is a typed name | Top residual risk; belongs with the local API and mobile app (next phase) |
| Review page is a static HTML file; decisions travel as a downloaded JSONL and recheck is a command | Next phase: the review interface as a mobile app on a local API server |
| The mentor-held 200 claims are unavailable | The oracle and stress tests are the substitute |
| Live AI answers not yet scored by a person (0/1 rubric in `outputs/llm_manual_scorecard.csv`) | Open, and now the most valuable missing evidence: it would settle which model and prompt reviewers prefer (`docs/21`) |
| Audit log tamper-evident, not immutable | Set `AUDIT_ANCHOR_KEY`, keep the anchor elsewhere, use write-once storage for real immutability (`docs/16`) |
| Architecture diagram, demo video, pitch, runbook | Not yet made |
| No overall budget cap on paid model calls | Documented (`docs/20`, LLM10) |

## 9. Working in this repository

**Set up and check** (see the README for details): `uv venv --python 3.10 .venv`, `uv pip install --python .venv -r requirements.txt`, then `python -m unittest discover -s tests`. It must pass, offline, before you push.

**Changing a rule.** The rulebook (`docs/04`, `rules/rules.json`) is the authority, not the code. Change `facts_extractor.py` and `rules/core.yar` together, add the case to the boundary table in `tests/test_stress_boundaries.py`, and run the differential tests: if the oracle disagrees, re-read the rulebook and decide which side is wrong before editing either. Then re-run `python scripts/verify_audit.py --log outputs/audit_dev/audit.jsonl --results outputs/yara_dev_predictions.jsonl` (after `run_yara.py`); a mismatch means you changed a result's content and the frozen audit sample needs regenerating on purpose.

**Do not:**
- edit `SHA256SUMS.json` (it is the organizers' integrity record; `validate_pack.py` failing on it is expected),
- commit `.env` or any key (a test scans tracked files),
- add `eval`, `exec`, `subprocess`, `pickle` or `shell=True` to `src/` or `scripts/` (a test fails),
- call the model from anywhere except through `explain_with_fallback`,
- present a PASS as approval, anywhere, in any wording.

**Experiments.** `python scripts/run_experiments.py` and `scripts/analyze_experiments.py` (needs `experiments/requirements-experiments.txt` and a `FEATHERLESS_API_KEY`). Write the metrics and decision rule down *before* a run, interleave the configurations you compare, and never change the default model, prompt or temperature without a new frozen run and a version note.

**Where to read next:** `docs/19` (how it was stress-tested and how each judged item is covered), `docs/20` (security), `docs/21` (experiments), `docs/17` (evaluation report).

## 10. Glossary

| Term | Meaning |
|---|---|
| Claim | A request for payment for services, here synthetic |
| Finding | One rule's result for one claim: PASS, FAIL, UNABLE_TO_ASSESS or NOT_APPLICABLE |
| UNABLE_TO_ASSESS | The data needed to decide is missing or unusable. Never shown as a pass |
| Evidence | A JSON pointer into the claim plus the exact value seen there |
| Facts blob | Text of facts the extractor produces per claim, which the YARA pack matches |
| Oracle | An independent reimplementation used to cross-check the engine |
| Grounding guard | A mechanical check that rejects model text asserting things the finding does not support |
| Anchor | A separate small file holding the audit chain's latest hash, to detect truncation or replacement |
| Advisory | A note about a defect the 15 rules do not cover; never a rule result |
