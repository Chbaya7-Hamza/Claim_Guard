# 27 | Every major decision: what we chose, what we rejected, the proof, and the honest weak spot

Every row points at evidence in this repo (a test, a script, a file, a figure). Where the evidence is weak or missing, it says so.
Numbers are copied from `SPECS.md`, `docs/19`, `docs/20`, `docs/24` and the project notes. Re-run the listed command before quoting any of them to a judge.

How to use this in a defense: state the decision in one sentence, give the proof, then volunteer the weak spot before being asked. A limit we name ourselves costs less than one a judge finds.

---

## A. Scope and principles

| Decision | Alternatives rejected | Proof | Weak spot and answer |
|---|---|---|---|
| **The rule engine decides, the AI only explains** (invariant I1) | Let the model judge claims end to end (what clinicProj does) | Schema check rejects any reply that changes status, rule id or review flag (`SPECS.md` §6). The injection variant VAR-02 flipped the review flag on Mistral-Nemo and on MedGemma, and the schema guard caught both, so it never reached a reviewer | *"The AI is wasted then."* It is used where it adds value: turning an engine sentence into plain language for a human. Verdicts need to be testable and repeatable, and a model cannot be |
| **Unknown is never a pass** (I2): missing or unusable data gives `UNABLE_TO_ASSESS` | Treat missing as pass, or guess | R009 is `UNABLE_TO_ASSESS` on all 310 FHIR claims that lack authorizations. Hostile-input tests: invalid UTF-8, 4,300-digit integers, 100,000-deep nesting, NaN, a 5 MB field | *"This creates many review items."* That is the correct cost. A false PASS in claims is worse than an extra review |
| **Synthetic data, fictional rulebook, no clinical or fraud judgement** | Real patient data, medical-necessity rules | `SPECS.md` §1. A guard against clinical/fraud wording was added and tested. A scan of all 4,198 recorded live answers found 0 real hits | *"Not realistic."* True, and by design for a student challenge. It also removes the privacy risk. Real data would need the privacy work listed in section F |
| **Original claim never modified, corrections rechecked as a new run** (I3) | Edit in place | Recheck writes its own audit trail and leaves the original untouched (`src/review_workflow.py`, tested) | None material |
| **Every step audited, AI question logged before the model is called** (I4) | Log only results | Audit verifier checks chain, anchor and AI ordering (`scripts/verify_audit.py`) | See the audit-log row below |

## B. Rule engine

| Decision | Alternatives rejected | Proof | Weak spot and answer |
|---|---|---|---|
| **YARA-X declarative rules** | The same 15 rules as plain Python functions | `python scripts/benchmark_yara_vs_python.py`. The benchmark shows **Python is about 11x faster** (1.752 ms vs 0.158 ms per claim on 20,000 claims). We say so openly | *"Then why YARA-X?"* Not speed: at 571 claims/s the engine is never the bottleneck, since the AI step takes seconds per call. The reason is structural. A YARA-X rule cannot make a network call, write a file, mutate state or loop forever, by construction. A Python rule can, and only author discipline stops it. Fault isolation is **not** a YARA-X advantage: a 5-line wrapper gives Python the same isolation. We tested that and reported it |
| **Fail closed per rule**: a crashing rule becomes `UNABLE_TO_ASSESS` for that rule only | Let the exception stop the claim | `tests/test_engine_robustness.py::IsolationTests`; injected R007 crash leaves the other 14 results unchanged | The engine stops the whole run if a rule has no outcome (extractor and pack out of sync). That is deliberate, because it means a build error, not bad data |
| **Percent-encode claim data before it becomes a fact** | Pass raw strings to the matcher | A value like `USD R009:MISMATCH:` cannot forge a finding for another rule (`SPECS.md` §5, tested) | None known |
| **Readings adopted where the rulebook is silent** (7 listed in `SPECS.md` §5) | Leave them implicit | Each has a test | These are our interpretations of the rulebook. If the organisers read a rule differently, the answer key is the arbiter. We match it 9,000 of 9,000 |
| **Strict dates `YYYY-MM-DD` on every Python version** | Accept whatever the interpreter accepts | Python 3.11+ accepts `20261231`; the rules reject it everywhere so verdicts do not depend on the interpreter | Stricter than some real systems. Acceptable for a fixed schema |

## C. Correctness proof

| Claim | Proof | Weak spot and answer |
|---|---|---|
| Engine is correct | Organisers' answer key: **9,000 of 9,000 results**, precision, recall and status accuracy 1.0 on all three splits. Handbook worked cases: 10 of 10 | Answer key is the arbiter wherever we read a rule differently from the organisers; we match it on all three splits |
| Not a one-sided test | Independent oracle (`tests/oracle.py`) rewrites all 15 rules from the rulebook alone and imports nothing from `src/`. **0 disagreements over 107,635 generated claims**, plus 37,000 boundary mutants and 123 hand-derived boundary cases (`scripts/status_coverage.py`) | The oracle was written by the same team, so a shared misreading of the rulebook is possible. The answer key is what covers that |
| Every status is reachable | Per-rule status coverage figure (`docs/figures/status_coverage.png`). A teammate's fuzzer never reached R009 PASS; we traced it to their seeding, reproduced with ours (23,627 of 107,635) | None |

## D. Audit log

| Decision | Alternatives rejected | Proof | Weak spot and answer |
|---|---|---|---|
| **Hash chain plus anchor file, optional HMAC** | Plain log file; a database table | Tamper tests; truncation and replacement detected by the anchor (`docs/16`) | **Tamper-evident, not immutable.** Without `AUDIT_ANCHOR_KEY`, someone who can write both files can rewrite both. We tested and documented it. Real immutability needs external storage |
| **Locking in `AuditLog.__init__`** | Retry the anchor read only | A 20-process benchmark found a real race; our first fix (retry) was incomplete, a reviewer showed a stale read could still cause a false failure. The real fix passed **10 of 10** runs. CI went green on all jobs for the first time after it | The CI explanation (2-vCPU runners made the race show every time) is strong circumstantial evidence, not a read job log. If CI goes red again, read the real log |

## E. The AI explanation step

| Decision | Alternatives rejected | Proof | Weak spot and answer |
|---|---|---|---|
| **Validate every reply, for every provider** (schema, citation repair, grounding guard, garbled-text guard) | Trust the model | Garbled but schema-valid answers were once accepted; the garble guard came from that observed failure. 47 of 49 recorded bad-citation rejections were formatting slips, so citation repair exists | The guards came from failures we observed. Unseen failure types are possible. The fallback (the engine's own sentence) bounds the damage |
| **Temperature 0** | Higher | E1: best on every quality measure; higher temperatures garbled more | Not word-for-word repeatable (stability 0.81 to 0.91). Verdicts do not depend on it |
| **Mistral-Nemo-Instruct-2407** (hosted) | 32B model; 7B terse setting; 14B | E2: the 32B had the worst live rate, 3 timeouts, 21 malformed replies. E5: the terse setting "wins" the metric by copying the engine's sentence. E7, E8: Nemo best on every measured dimension | The hosted endpoint drifts (the same 14B config scored 78.7%, 76.9%, 59.8% in three runs), so only interleaved runs compare fairly. Nemo's value-citation was 45.8% against a 50% bar, and we overrode that rule by judgement and said so |
| **Prompt v1.6.0 plus closing gate** | v1.4.0, v1.5.0 | E10b: the only arm with all seven benchmarks at 85% or more (lowest 93.2%), 12 new cases, 10 repeats, 120 answers per arm. Rule followed, no override | Prompts were written while looking at tuning-set answers. Confirmation used unseen cases. Two benchmarks were redefined before the runs; old definitions still reported |
| **Local model `gemma3:4b` for on-prem** | `qwen3:4b`, `medgemma-4b-it` | 97.2% live (35/36), median about 3 s, 84-case stress test with 0 garbled. MedGemma 83.3% and about 4x slower. Qwen3: no `max_tokens` value worked on the whole set, one case needed 4,613 tokens, others exceeded 8,000 and the timeout | The rates are on 36 cases (plus an 84-case stress run for gemma3). Automated metrics only; they are mechanical proxies, stated as such in `SPECS.md` §11.8 |
| **Two deployment modes**: hosted Nemo by default, local gemma3 for on-prem | One model only | Both go through the same validation path (`SPECS.md` §6a) | A judge may ask which one is "the" model. Answer: hosted is the tested default; local is the on-prem option the mentor asked for |
| **Cascade available, not default** | Default cascade | E8: tier 2 was never exercised, so there is no evidence to justify making it default | None |

## F. Security

| Decision | Proof | Weak spot and answer |
|---|---|---|
| **Audit against OWASP Top 10 (web) and Top 10 for LLM apps** | `docs/20_Security_Audit.md`; Bandit and adversarial suites in CI | **No authentication or RBAC yet.** Reviewer identity is self-declared. This is our largest open security gap and it is on the plan (step 8 of doc 26) |
| **No `eval`, `exec`, `subprocess`, `pickle` in our code** | A test scans `src/` and `scripts/` | The comparison's clinicProj copy has two sink matches (the calculator `eval`, a bare `input()`), reported as such in doc 24 |
| **Pinned dependency revisions** | Bandit found an unpinned model download (B615); pinned to the tested commit. `pip-audit` clean | None known |
| **Secrets kept out of prompts, logs and records** | `.env` ignored and scanned | With real data, protected health information would go to a third-party model. That is why on-prem serving matters (plan step 11) |
| **No per-run spending cap** | (none) | Stated residual risk |

## G. Verification and delivery

| Decision | Proof | Weak spot and answer |
|---|---|---|
| **477 offline tests (420 verified on Python 3.10, 3.12, 3.14 in CI)** | CI green on all 6 jobs at commit `0aac644`, when the suite was 420 tests; the 57 added since ran on 3.10 locally | CI was red on every run from its first commit until the audit-lock fix. We found it, fixed it and say so, rather than hiding it |
| **Demo is offline and scripted** (`scripts/demo.py`, 8 scenes, about 2 s) | Video kit in `docs/23` | Video is being filmed from that script |

## H. Architecture comparison (ClaimGuard vs clinicProj)

| Decision | Proof | Weak spot and answer |
|---|---|---|
| **Both systems on the same model** | Harness in `comparison/`, deterministic scoring script, recorded rows | The first run used `gemma3:4b`, which has no tool-calling. clinicProj failed all 36 claims, so the 96.67 vs 13.33 result measured the model, not the architecture. **Do not present that as a fair win.** We are re-running on a tool-capable model (`docs/25`) |
| **Scored by formulas from measurements, not typed in** | Reviewer caught two flaws (ClaimGuard security assumed 100; a system that failed everything also "won" rapidness). Both fixed before the numbers were published | ClaimGuard's 100% correctness is guaranteed by construction, since CI already demands a perfect score on that split. Stated in doc 24 |
| **Weights: correctness 30, security 20, deliverability 20, rapidness 15, efficiency 15** | Chosen to follow the mentor's stated priorities | The weights are our judgement. If a judge changes them, the scoring script re-ranks in one run |
| **Hallucination metric added** | `hallucination_score` in `scripts/score_clinicproj_comparison.py`: fabricated findings (a FAIL the key says did not fail, or an invented rule id) and ungrounded evidence values, averaged; unit-tested in `tests/test_comparison_additions.py` | The metric is not specific enough | Built and used in doc 24. The clinicProj side rests on 4 answered claims, so its 66.0 is indicative only |

---

## I. Experiment behind every decision

A rationale is not proof. Each decision needs a measurement that could have gone the other way.
"Exists" means it is already in the repo and cited above. "To run" is a designed experiment, not yet run, so it has no result here.

| Decision | Experiment | Hypothesis that could fail | Status |
|---|---|---|---|
| Declarative rules (YARA-X) over Python | `scripts/benchmark_yara_vs_python.py`: speed, fault isolation, size | YARA-X is faster or safer | Exists. It failed on speed; the structural argument stands alone |
| Rules match the standard | Answer key, 9,000 results; oracle on 107,635 claims | Engine disagrees with key or oracle | Exists, 0 disagreements |
| Percent-encoding of facts | `scripts/defense_experiments.py injection`: 20 claims, 47 real fact lines as payloads, 3 shapes each, injected into every string field. A rule counts as forged if its status changes beyond what a harmless value in that field changes | Forged value changes another rule's result | **Run.** With encoding: **0 of 32,148** trials forged an outcome. Without encoding (same trials): **6,105 of 32,148** did. Engine crashes: 0 in both. Limit: a forged outcome is only counted in rules a harmless value in that field does not also change, so a forgery landing on a rule the field legitimately affects (for example `patient_id` and R004) would not be seen; the 0 is 'none found in the rules that could be tested', and the 6,105 is a floor. Raw: `outputs/defense/injection.json` |
| Fail closed to `UNABLE_TO_ASSESS` | `defense_experiments.py failclosed`: each of the 15 rules made to raise, over 100 claims | A crash lets a claim through | **Run.** 15 of 15 rules: crashed rule was `UNABLE_TO_ASSESS` on every claim, never PASS, and the other 14 results never changed. Raw: `outputs/defense/failclosed.json` |
| Hash-chained audit log | `defense_experiments.py tamper`: 9 attacks against a chain-only verifier, a chain-plus-anchor verifier, its strict mode, and strict with an HMAC key | Some tampering goes undetected | **Run.** See the table below the map. Chain alone catches edit, delete and swap. The anchor adds truncation and edit-and-rechain. The HMAC key adds full rewrite of log and anchor. Appending forged rows with a valid chain was caught by none of them until a strict anchor check was added; now it is caught (strict), and a forged anchor as well with a key |
| Audit lock | 20-process concurrency benchmark, before and after the fix | Race persists | Exists, 10 of 10 after the fix |
| Validation layers (schema, citation repair, grounding guards, garble guard) | `defense_experiments.py ablation`: every recorded raw reply from `experiments/raw/` (4,040 parsed) replayed through each guard on its own, with the real validators on the original findings. The full stack agrees with production `check_grounding`/`validate_explanation` on all 4,040 (0 mismatches) | A layer catches nothing | **Run.** 114 replies rejected in total. Schema: 72. Relative-time: 19. Validity: 16. Currency: 4. Garbled: 3. **Clinical/fraud: 0.** Citation repair rescued 73 that would otherwise have been rejected. In this replay every rejected reply failed exactly one layer, but that is partly by construction: a reply the schema rejects never reaches the grounding checks, so the schema count is schema rejections, not replies only the schema could catch. The four grounding guards that fired (relative-time, validity, currency, garbled) each caught replies that passed the schema. The clinical/fraud guard has never fired on real data; it stays as a scope guard, and we do not claim it catches anything. Raw: `outputs/defense/ablation.json` |
| Temperature 0, model, prompt, closing gate | E1 to E10b, interleaved, unseen confirmation cases | Another setting wins | Exists |
| Local model `gemma3:4b` | 4-model comparison and 84-case stress run | Another local model wins | Exists |
| AI explanation over the engine's own sentence | `defense_experiments.py aivstemplate`: the project's own E10b scoring functions applied to the final AI arm (117 live answers, 12 unseen cases) and to two template baselines: the engine sentence alone, and the engine sentence plus the `corrective_action` field a reviewer sees anyway | The AI adds nothing over the template | **Run.** Cites a value from the evidence: AI **93.2%**, template **8.3%** (either baseline). States the corrective action: AI 100%, template alone 25%, **template plus action field 100% (a tie)**. Mean length 30.4 words vs 6.7 and 17.0. So the measured advantage is value citation, not the action. Raw: `outputs/defense/aivstemplate.json` |
| Ingestion robustness | Hostile-input battery (UTF-8, huge ints, deep nesting, NaN, 5 MB fields) | Crash or silent pass | Exists |
| Security posture | OWASP audit, Bandit, adversarial suites, injection variants | New finding | Exists |
| Architecture vs clinicProj | Same-model harness (Qwen2.5-14B on both), 12 claims, scored by formula, strict and lenient parsing both reported | The other architecture wins | **Run.** ClaimGuard 97.5 vs clinicProj 11.5 strict / 21.1 lenient, ClaimGuard ahead in every category. **Limits stated in doc 24:** 10 of clinicProj's 12 runs hit endpoint failures, so its numbers are a floor for this run, not its best case; ClaimGuard's correctness and hallucination scores are structural; one injection probe flipped clinicProj's verdict to VALID |
| Precedence `FAIL > UNABLE_TO_ASSESS > NOT_APPLICABLE > PASS` | `defense_experiments.py precedence`: all 24 orders scored against the answer key (6,000 results) and against the independent oracle (75,000 results on 5,000 generated claims) | A different order matches the key better | **Run, and it does not discriminate.** All 24 orders: 0 disagreements on both. A direct check on 3,000 generated claims found **no rule ever emits more than one outcome**, so the order is never exercised by any data. The order is a safety policy (a proven violation must beat a pass), not a result these experiments can prove. Say so if asked |
| Performance and scaling | `defense_experiments.py load` | Throughput collapses, or the AI step dominates | **Run.** Engine: 1,391 claims/s at 1,000 claims, 1,345 at 5,000, **611 at 20,000**. A follow-up profile showed this is machine noise, not a scaling limit: within one 20,000-claim run the rate swung between about 520 and 1,340 claims/s with garbage collection on or off, so quote the engine as roughly 500 to 1,300 claims/s per core on this laptop. Audit append: 2,647 events/s; verifying 2,000 events took 0.08 s. AI step: median 2.86 s, **p95 28.9 s** (117 live calls). At the 20,000-claim rate the median AI call is about **1,750 times** the engine's per-claim time, so the AI step is the bottleneck and the queue decision should be about it. Raw: `outputs/defense/load.json` |

Caveats on the ablation: 466 of the recorded raw replies did not parse as JSON under this script's simple parser and were left out (the production provider may accept some of them, so the 4,040 is a floor, not the full set). The relative-time guard also fires on words like "currently" in a sentence about document status (example: EX-19, "currently in draft status"), which is arguably a false positive; we have not measured the false-positive rate of the guards and do not claim one.

Caveat on AI vs template: both are mechanical proxies on 12 cases. They show the AI quotes the evidence; they do not show a reviewer finds the AI text clearer. Three of 120 gated calls were rejected and fell back to the template, which is the designed floor.

Audit-log append profile: 55% of an append's time is rewriting the anchor file (0.38 s of 0.68 s over 200 appends). Writing the anchor once per 10 appends raised throughput from about 4,400 to about 11,100 events/s. That is a speed-up with a security cost (truncation between anchors goes unnoticed), so the safer route is writing one batch of several claims per append, which keeps an anchor after every append.

Caveats on the comparison metrics (from the final code review): the hallucination score is computed only over claims a system actually answered, so a system that answers few claims is barely penalised beyond the no-answer case, and a parseable reply with an empty `findings` list scores 100; in the evidence-grounding check a clinicProj evidence item with no `value` key counts as ungrounded while ClaimGuard's non-scalar values are skipped, and the substring fallback makes very short strings count as grounded. Treat the hallucination category as indicative on its current base (4 answered claims) and do not quote its number as a rate.

### Audit-log tamper matrix (detected = yes)

"Strict" is the offline check `verify_with_anchor(..., strict=True)` that `scripts/verify_audit.py` now runs by default; it also rejects rows after the anchored position. The first version of this experiment, before strict mode existed, showed appended forged rows undetected by every verifier. That gap was found here and closed in the same session.

| Attack | Chain only | + anchor | + anchor, strict | + anchor, strict, HMAC key |
|---|---|---|---|---|
| Edit one row, no rechain | yes | yes | yes | yes |
| Delete a middle row | yes | yes | yes | yes |
| Swap two rows | yes | yes | yes | yes |
| Truncate the tail | no | yes | yes | yes |
| Edit a row and recompute the chain after it | no | yes | yes | yes |
| Rewrite the chain and the anchor together (attacker has no key) | no | no | no | yes |
| Append forged rows with a valid chain, anchor untouched | no | no | **yes** | yes |
| Append forged rows, then rewrite the anchor (no key) | no | no | no | yes |
| Rewrite the log and sign a forged anchor with a stolen HMAC key | no | no | no | **no** |

What this shows and what it does not: without a key, anyone who can write both files can still rewrite the whole log and its anchor (rows 6 and 8), exactly as `docs/16` already says. The HMAC key closes that, provided the key is not on the machine the writer runs on; an attacker who holds the key defeats it (last row), so the key must live outside the writer's reach (docs/28, item 7). The strict check only applies to a log no writer is appending to: a live reader can catch a writer between its log write and its anchor write, so `AuditLog.__init__` keeps the non-strict check (tested in `tests/test_audit_strict_anchor.py`). Raw: `outputs/defense/tamper.json`.

## J. Roadmap (not gaps)

Planned work, each with its proof of success in doc 26: authentication and RBAC, web review interface, async queue with Redis, local model serving as a deployed service, NoSQL store, demo video (being filmed), pitch.
