# 24 | ClaimGuard vs. clinicProj: an architecture comparison

Mentor-requested comparison between ClaimGuard's own deterministic-rules-plus-
grounded-AI architecture and a teammate's separately-built RAG+OCR+agentic
system (`github.com/ayechiahmed/clinicProj`). Full methodology and rationale:
`docs/superpowers/specs/2026-09-28-clinicproj-architecture-comparison-design.md`.
Reproduce this yourself: `comparison/README.md`.

## Headline finding, stated first because it drives every number below

**clinicProj's architecture cannot run at all on gemma3:4b, the local model
ClaimGuard's team chose.** Every one of the 36 sampled claims failed
identically with `openai.BadRequestError: registry.ollama.ai/library/gemma3:4b
does not support tools`. Confirmed structurally, not just empirically, via
Ollama's own capability listing (`ollama show gemma3:4b` / `/api/show`):
gemma3:4b reports `['completion', 'vision']` — no `tools` — while another
locally-pulled model, qwen3:4b, reports `['completion', 'tools', 'thinking']`.
clinicProj's agent is a LangGraph ReAct agent built on OpenAI-style
tool-calling (`retrieve_documents`, `calculator`); that is not a bug in this
comparison's harness, it is a hard capability gap in the model.

We did **not** switch clinicProj to a different, tool-capable local model
(e.g. qwen3:4b) to get it running — that would reintroduce "different model"
as a confound and defeat the point of wiring both systems to the same one. We
also did not rewrite clinicProj's agent to drop tool-calling (e.g. a manual
retrieve-then-prompt pipeline) — that would be changing its actual
architecture, not comparing it. Both would have produced a more flattering
number for clinicProj and a less honest comparison. See "Verdict" below for
what this means and does not mean.

## What each system is

**ClaimGuard** (this repo) runs `data/development/claims.jsonl` claims
through 15 deterministic YARA-X rules (`src/run_yara.py`); each FAIL or
UNABLE_TO_ASSESS finding then gets a grounded, schema-checked AI explanation
(`src/llm_adapter.py`) from a local gemma3:4b via Ollama. The AI never
decides status — it explains a deterministic verdict, with citation-grounding
and closing-gate checks enforced in code — and every step is written to a
tamper-evident hash-chained audit log before the next step runs.

**clinicProj** (`comparison/clinicproj_adapted/`, adapted only to swap its
LLM binding from cloud Gemini to local gemma3:4b — see `comparison/README.md`)
is a LangGraph ReAct agent. Claim documents go through `extractor.py`
(Tesseract OCR for images/scanned PDFs, then an LLM call to turn raw text
into structured claim JSON); payer policy text is chunked and embedded
(`all-MiniLM-L6-v2`) into a FAISS index; the agent has a `retrieve_documents`
tool for semantic search over that index plus a regex-sandboxed `calculator`
tool. The agent itself — not any deterministic layer — decides rule matches,
severity, confidence and recommendations, driven entirely by one large system
prompt. There is no audit log, no persistence layer, no test suite, no CI,
and no schema validation of the agent's own output; `server.py` in the
original repo is empty (unimplemented).

## Methodology

- Both systems wired to the identical local model: gemma3:4b via Ollama
  (`http://localhost:11434`), the same endpoint and model ClaimGuard's own
  `OllamaExplanationProvider` already used before this comparison existed.
- Sample: 36 claims from `data/development/claims.jsonl` — the same
  sample size used in prior model-comparison experiments (`docs/21`), run in
  full; clinicProj's per-claim failures were near-instantaneous (see
  "Rapidness" below), so there was no latency-budget reason to sample smaller.
- clinicProj's `policies/` folder was given a complete, honest prose
  rewrite of all 15 CSTAM rules (`comparison/clinicproj_adapted/policies/cstam_rulebook.txt`),
  not left with only its one throwaway sample policy — otherwise this would
  measure "how does the agent behave with nothing real to retrieve," not a
  fair test of its RAG capability.
- Scoring: `scripts/score_clinicproj_comparison.py`, a deterministic,
  rerunnable script — not a number typed into this document by hand. Weights
  (correctness 30, security 20, deliverability 20, rapidness 15, efficiency
  15) and their rationale are in the design spec's "Who wins benchmark
  scoring" table, chosen to track the mentor's own stated evaluation
  priorities where they overlap.

## Results

![Category scores](figures/architecture_comparison_categories.png)

| Category | ClaimGuard | clinicProj | Winner |
|---|---|---|---|
| Correctness | 100.0 | 0.0 | ClaimGuard |
| Security | 100.0 | 35.0 | ClaimGuard |
| Deliverability | 100.0 | 16.67 | ClaimGuard |
| Rapidness | 0.80 | 100.0 | clinicProj — **see caveat below** |
| Efficiency | 81.25 | 0.0 | ClaimGuard |

![Overall verdict](figures/architecture_comparison_overall.png)

**Overall weighted score: ClaimGuard 82.31, clinicProj 25.33 — ClaimGuard
wins**, including after clinicProj's rapidness category win is weighted in.

**Rapidness caveat, stated plainly because the number alone is misleading:**
clinicProj's 100.0 does not mean it answered quickly — every one of its 36
claims failed in under 0.1s (one took 2.1s, to establish the connection;
every claim after that failed in effectively 0.0s) because the tool-calling
request was rejected before any actual reasoning happened. It is fast because
it did not run, not because it is efficient. ClaimGuard's 0.80 reflects real
work: 36 real deterministic rule evaluations plus AI explanations for every
flagged claim, with real gemma3:4b latency up to 48s on the most complex
case. A reasonable person reading only the bar chart would draw the wrong
conclusion; this paragraph exists so a mentor's question about it has an
honest answer already on the page.

**Correctness:** ClaimGuard matched the answer key's claim-level status
(VALID / REVIEW_REQUIRED / INVALID, derived the same way for both systems —
methodology detail: any FAIL row makes a claim INVALID, any UNABLE_TO_ASSESS
without a FAIL makes it REVIEW_REQUIRED, otherwise VALID) on all 36 sampled
claims. clinicProj scored 0.0 — not because its reasoning is worse, but
because it produced no answer for any claim (see headline finding).

**Security:** `scripts/security_scan_clinicproj.py --live` found, against
`comparison/clinicproj_adapted/`: two dangerous-sink matches (`eval()` in the
`calculator` tool — regex-prechecked to digits/operators only, so real risk
is low, but still a flagged pattern; and a bare `input()` call in the CLI's
interactive follow-up loop), no citation-grounding guard (clinicProj has no
equivalent of ClaimGuard's `check_grounding()`/`_UNGROUNDED` check — nothing
in code verifies an AI explanation's claims are backed by real evidence after
the fact), and the prompt-injection resistance probe itself could not run for
the same tool-calling reason as the correctness run (scored as a real
deduction, not a free pass — see the design spec's security scoring rules).

**Deliverability:** a plain checklist (audit log, test suite, CI,
auth/RBAC design, offline capability, schema-validated output) — clinicProj
has offline capability and nothing else on this list yet; it is early-stage
work (a single "Initial commit," no CI, `server.py` unimplemented), which is
a fair and expected state for that stage, not a criticism of the person who
built it.

**Efficiency:** a dependency-count proxy (fewer third-party runtime
dependencies scores higher) — ClaimGuard's `requirements.txt` has 3 pinned
packages; clinicProj's inferred `requirements.txt` has 16 (none existed
upstream). Not a token-cost measure: neither provider reliably reports
tokens for every call in this setup.

## What clinicProj does that ClaimGuard doesn't

OCR (Tesseract, scanned PDFs and images), a multi-turn conversational Q&A
interface over a validated claim, and a general-purpose RAG layer that can
ingest arbitrary policy documents without code changes. This comparison's
claim sample was pre-structured JSON, not scanned documents, so OCR itself
was not empirically exercised here — it's a real capability gap in
ClaimGuard today, tracked separately (`docs/superpowers/specs/` mobile-app
architecture notes), not something this comparison resolves either way.

## What ClaimGuard does that clinicProj doesn't

A deterministic rule layer the AI cannot override, schema-checked and
citation-grounded AI explanations, a tamper-evident audit log, a test suite
and CI, and no dependency on the LLM to correctly parse its own output
format or to support tool-calling at all.

## Verdict

**ClaimGuard's architecture wins overall, 82.31 to 25.33, and wins 4 of 5
individual categories outright** (correctness, security, deliverability,
efficiency). clinicProj's one category win (rapidness) is an artifact of
failing fast, not evidence of a faster real system — stated above, not
smoothed over.

The single most important, generalizable finding is not "ClaimGuard's rules
are better than clinicProj's prompt" — that comparison never actually ran,
because clinicProj's chosen architecture (an agentic RAG system built on
tool-calling) has a hard dependency the team's chosen local model does not
meet. That is itself the architectural lesson: a design that depends on a
specific model capability (tool-calling) is more fragile to a local-model
choice than a design that only ever asks a model to produce and explain
text, exactly ClaimGuard's approach. This directly reinforces the mentor's
point 8 (fully local/on-prem deployment) — an architecture that assumes a
capability its deployment target's models don't reliably have is a real
production risk, not a hypothetical one.
