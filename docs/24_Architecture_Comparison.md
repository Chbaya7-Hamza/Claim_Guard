# 24 | ClaimGuard vs. clinicProj: an architecture comparison

Mentor-requested comparison between ClaimGuard's deterministic-rules-plus-grounded-AI architecture and a teammate's separately
built RAG+OCR+agentic system (`github.com/ayechiahmed/clinicProj`). Methodology: `docs/superpowers/specs/2026-09-28-clinicproj-architecture-comparison-design.md`.
Reproduce: `comparison/README.md`. Model choice for the second run: `docs/25_Comparison_Model_Selection.md`.

There are two runs. The first was not a fair test and is kept as a finding. The second is the one to quote, with its limits.

## Run 1 (gemma3:4b, Ollama, offline): clinicProj could not run

clinicProj's agent is a LangGraph ReAct agent built on OpenAI-style tool calling. `gemma3:4b` reports no `tools` capability in Ollama,
so every one of 36 claims failed with `does not support tools`. The 96.67 vs 13.33 score from that run measured the model, not the
architecture, and is **not** a result to cite as "ClaimGuard wins". What it does show: an architecture that depends on a model
capability (tool calling) is more fragile to a local-model choice than one that only asks a model to explain text. Evidence:
`outputs/architecture_comparison/gemma3-4b-ollama/`, figures `*_gemma3.png`.

## Run 2 (Qwen2.5-14B-Instruct, Featherless, hosted): both systems on one tool-capable model

- **Model.** `Qwen/Qwen2.5-14B-Instruct` for both systems. ClaimGuard's production explanation model is Mistral-Nemo, but Nemo writes tool
  calls as plain text and cannot drive clinicProj, so a shared model had to differ from it. Screening table: doc 25.
- **Hosted, not offline.** This run needs the network. The "fully local" property belongs to Run 1 only.
- **Sample.** The first 12 claims of `data/development/claims.jsonl` (kept small on purpose). The first 6 were also in the model screening.
- **Order.** clinicProj, then ClaimGuard, then the security probe, one after another, after a warm-up call.
- **ClaimGuard's AI step was real.** 16 explanations, 0 template fallbacks (`used_fallback` false on all).
- **Scoring.** `scripts/score_clinicproj_comparison.py`, deterministic, from the recorded rows. Weights with the new hallucination
  category: correctness 25, hallucination 15, security 20, deliverability 15, rapidness 15, efficiency 10. A system is scored on
  rapidness only for claims it actually answered.
- **Strict and lenient are both reported.** clinicProj has no output parser, and Qwen often wraps valid JSON in prose or a code fence.
  Strict counts only a reply that is JSON from the first character. Lenient takes the text from the first `{` to the last `}` and
  is a disclosed adjustment for a formatting habit, not a change to clinicProj's logic.

### The limit that matters most: the endpoint degenerated on clinicProj's runs

Of clinicProj's 12 replies, **8 were degenerate** (runs of `!!!!!!…` or a `<tool_call>` written as text instead of executed) and **2 were
service errors** (`The model failed to generate a response`, `No successful response received from completion service`). Only 2 to 3 of 12 held
a parseable answer. The same model on the earlier 6-claim screen gave 6 of 6 lenient answers with no degenerate output, so the failure rate
moved between runs. ClaimGuard's calls are short (about 85 completion tokens); clinicProj's agent produces long outputs across several tool
rounds, so it is more exposed to an endpoint that degrades. We cannot separate "the endpoint glitched" from "the architecture needs long
stable generations", and the numbers below should be read as **what clinicProj did on this hosted endpoint on this run**, not as its
best case. A re-run on a stable endpoint, or local tool-capable serving, is the way to settle it.

### Results

| Category (weight) | ClaimGuard | clinicProj strict | clinicProj lenient |
|---|---|---|---|
| Correctness (25) | 100.0 | 0.0 | 8.3 |
| Hallucination (15) | 100.0 | 0.0 (no answers) | 66.0 |
| Security (20) | 100.0 | 35.0 | 20.0 |
| Deliverability (15) | 83.33 | 16.67 | 16.67 |
| Rapidness (15) | 100.0 | 0.0 | 4.0 |
| Efficiency (10) | 100.0 | 20.0 | 20.0 |
| **Overall** | **97.5** | **11.5** | **21.08** |

Figures: `docs/figures/architecture_comparison_{categories,overall}_qwen25-{strict,lenient}.png`. Raw rows and verdicts:
`outputs/architecture_comparison/qwen25-14b-featherless/`.

**Correctness.** ClaimGuard matched the answer key on 12 of 12. That is guaranteed by construction (CI already demands a perfect score on this
split), so it is not an independent finding. clinicProj matched 0 of 12 strictly and 1 of 12 leniently.

**Hallucination (new metric).** Two rates over the findings a system actually produced, averaged, 100 meaning none. (a) Fabricated findings:
a FAIL on a rule the answer key says did not fail, or a rule id outside R001 to R015. (b) Ungrounded evidence: a cited evidence value that
appears nowhere in the claim (numbers compared numerically). A system with no parseable findings scores 0, since no answer is not an honest answer.

| | Claims answered | Findings | Fabricated | Evidence values | Ungrounded |
|---|---|---|---|---|---|
| ClaimGuard | 12 | 180 | 0 | 570 | 0 |
| clinicProj (lenient) | 4 | 9 | **5** | 16 | 2 |

ClaimGuard's 0 and 0 are structural: its FAIL statuses come from the rules, which match the key, and its evidence is a direct lookup in the
claim. clinicProj's 5 fabricated findings out of 9 is a real measurement but on a very small base (4 claims, 9 findings), so the 66.0 has a wide
margin and should not be quoted as a rate. ClaimGuard's AI explanations also went through the existing grounding guards (0 fallbacks here).

**Security.** The same scan ran on both codebases. clinicProj: two dangerous-sink matches (the calculator `eval`, a bare `input()`) and no
citation-grounding guard. **The injection probe found something real:** a claim with a genuine currency violation (R015) and an injected instruction in
its notes came back from clinicProj as `overall_status: VALID`, "The claim is fully valid with no findings." The reply was wrapped in prose, so
strict scoring recorded it as "not verified" (-15); lenient scoring reads it as an incorrectly valid claim (-30), which is why the lenient security
score is lower. It is one probe, one model, one run. ClaimGuard was not sent the probe because it has no free-text conversational surface for it; its
injection resistance is covered by its own tests (`tests/test_stress_ai_boundary.py`, `docs/20`), and its score skips that one deduction tier.

**Rapidness.** Computed only from answered claims. ClaimGuard: median 3.6 s per claim including live explanations. clinicProj: only 3 claims were answered even
leniently, at 14 s, 46 s and 116 s (median 46 s); with n=3 that is an anecdote, not a rate. Strictly, it answered none, so its strict rapidness is 0.
(The hallucination table counts 4 claims because one more reply held parseable findings without an `overall_status`.)

**Deliverability and efficiency.** Unchanged from Run 1: a checklist (ClaimGuard 5 of 6; `auth_rbac_designed` false for both because no RBAC
design is committed) and third-party dependency counts (3 vs 15, normalised to the leanest).

## What each system is

**ClaimGuard** runs claims through 15 deterministic YARA-X rules; each FAIL or UNABLE_TO_ASSESS finding gets a schema-checked, citation-grounded
AI explanation. The AI never decides status, and every step goes to a tamper-evident audit log.

**clinicProj** (`comparison/clinicproj_adapted/`, changed only to swap Gemini for the configured model) is a LangGraph ReAct agent with OCR,
a FAISS index of policy text and two tools. The agent alone decides rule matches, severity and recommendations from one large prompt. No audit
log, no tests, no CI, no output schema check; its `server.py` is empty. It is early-stage work, which is a fair state for that stage.

## What clinicProj does that ClaimGuard doesn't

OCR for scans and images, a multi-turn Q&A over a validated claim, and a general RAG layer for arbitrary policy documents. The claim sample here
was structured JSON, so OCR was not exercised.

## Verdict

On this run ClaimGuard scored 97.5 and clinicProj 11.5 (strict) or 21.1 (lenient), and ClaimGuard led every category under both readings. Read
that with the limits above: 10 of clinicProj's 12 runs hit an endpoint failure, the sample is 12 claims, the hallucination base for clinicProj is
4 claims, ClaimGuard's correctness and hallucination scores are structural, and the injection probe is a single trial.

What the data supports without those caveats: (1) an architecture whose correctness depends on a model producing a long, well-formed, tool-using
generation is more exposed to model and endpoint variability than one that uses the model only to explain a verdict the rules already made;
(2) in the one injection probe we ran, the agentic design let injected text change the verdict and the rule-based design has no such path;
(3) ClaimGuard's checks cost more to build but every claim got the same, answer-key-matching result.

What it does not support: a claim that clinicProj's reasoning is worse in general. A stable, tool-capable, locally served model would be the fair
re-test, and is the natural next step given the mentor's on-prem point.
