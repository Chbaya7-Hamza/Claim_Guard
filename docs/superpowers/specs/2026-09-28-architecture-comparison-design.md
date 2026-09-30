# Architecture A vs. Architecture B architecture comparison — design

Date: 2026-09-28
Status: approved (chat design approved by user; spec pending user review)
Scope: a self-contained comparison subsystem, not a change to Architecture A's own engine.

## Purpose

The mentor (Dr. Wael Hilali) asked the team to compare two competing architecture
decisions: Architecture A's own deterministic-rules-plus-grounded-AI design, and a
teammate's (Ahmed's) separately-built system at `a teammate's repository`
— a RAG + OCR + LangGraph agentic-reasoning design. The goal is a defensible,
reproducible verdict the team can stand behind under mentor questioning: which
architecture is stronger, on what axes, and why — not a hand-wavy writeup.

This is scoped as its own subsystem: a copy of Architecture B's code (adapted only to
use Architecture A's local model instead of a cloud one), a benchmark harness that runs
both systems over the same claims, scoring/plotting scripts, and a comparison
document. It does not touch Architecture A's own engine, rules, or audit log.

## What each system actually is (read directly from the code, not assumed)

**Architecture A** (this repo): `data/{development,validation,stress}` claims (600,
with an answer key) run through 15 deterministic YARA-X rules
(`src/run_yara.py`), each FAIL/UNABLE_TO_ASSESS finding then gets a grounded,
schema-checked AI explanation (`src/llm_adapter.py`) from a local model via Ollama
— currently gemma3:4b. The AI never decides status; it explains a deterministic
verdict, with citation-grounding and closing-gate checks enforced in code, all
logged to a tamper-evident hash-chained audit log.

**Architecture B** (`a teammate's repository`, cloned read-only into
`comparison/architecture_b_original/` for reference): a LangGraph ReAct agent, currently
wired to cloud Gemini (`gemini-3.1-flash-lite`, needs `GOOGLE_API_KEY`). Claim
files (PDF/DOCX/XLSX/CSV/image) go through `extractor.py` — Tesseract OCR for
images and scanned PDFs, then an LLM call (`extract_claim_json`) turns raw text
into structured JSON. Payer policy documents are chunked (500 chars, 50 overlap)
and embedded (`all-MiniLM-L6-v2`) into a FAISS `IndexFlatL2` store; the agent has
a `retrieve_documents` tool for semantic search plus a sandboxed `calculator`
tool (`eval()` on a regex-prechecked arithmetic-only string). The agent itself —
not any deterministic layer — decides rule matches, severity, confidence, and
recommendations, driven entirely by one large system prompt. No audit log, no
persistence layer, no tests, no CI; `server.py` is empty (unimplemented).

Per the user's explicit direction: **no artificial leveling.** We compare both
systems as complete, real architectures, exactly as each currently works. If
Architecture B can't function without OCR/RAG, that's a property of its architecture,
not something to strip out for "fairness."

## Non-goals

- Not modifying Architecture A's own engine, rules, or audit log.
- Not pushing anything to `a teammate/Architecture B` — no write access, and it
  would not be appropriate regardless. All deliverables land in this repo only.
- Not trying to make Architecture B's RAG retrieve the literal CSTAM rulebook wording
  in a way that biases it toward matching Architecture A's exact rule IDs — its
  `policies/` folder gets a good-faith, complete prose encoding of the 15 rules
  (see Data & methodology), not a version secretly optimized to make it agree
  with Architecture A's answers.

## Components

1. **`comparison/architecture_b_original/`** — the cloned Architecture B repo, read-only
   reference copy (already present locally;
   this is a copy of it committed into Architecture A's own repo so the comparison is
   reproducible without depending on the external clone staying available).
2. **`comparison/architecture_b/`** — a working copy of just the files
   Architecture B's code actually imports (`agent.py`, `extractor.py`,
   `document_loader.py`, `policies/`), stripped of personal scratch files
   (`aaa.jpg`, `claim1.png`, `claim2.png`, `sample.*`, `.vscode/`) that nothing
   imports. Two changes only:
   - A new `requirements.txt` (none exists upstream) inferred from the actual
     imports: `faiss-cpu`, `sentence-transformers`, `langchain`, `langgraph`,
     `langchain-openai` (replaces `langchain-google-genai`), `pytesseract`,
     `pdfplumber`, `python-docx`, `pandas`, `openpyxl`, `Pillow`, `pypdfium2`,
     `python-dotenv`.
   - `agent.py` and `extractor.py`'s LLM construction swapped from
     `ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite")` to
     `ChatOpenAI(base_url="http://localhost:11434/v1", api_key="ollama-local",
     model="gemma3:4b")` — the exact same local Ollama endpoint and model
     Architecture A's own `OllamaExplanationProvider` already uses, so both systems
     hit the literal same model instance. No other logic changes: same
     ReAct-agent structure, same prompt, same RAG, same OCR path.
3. **`comparison/policies/cstam_rulebook.txt`** — a complete prose encoding of
   all 15 rules from `docs/04_Rulebook.md`, written the way a real payer policy
   document would read (not copy-pasted rule IDs), for Architecture B's RAG to
   actually retrieve against. Without this, Architecture B has nothing real to
   validate against beyond its one throwaway sample policy.
4. **`scripts/run_architecture_comparison.py`** — drives both systems over the
   same claim sample from `data/{development,validation,stress}`, records for
   each claim: wall-clock latency, token usage (where available), the raw
   output, and — for Architecture A — reuses `src/evaluate.py`'s existing scoring
   against the answer key. Writes one JSONL per system to
   `outputs/architecture_comparison/`.
5. **`scripts/score_architecture_comparison.py`** — the benchmark/"who wins" step
   the user asked for. Reads both JSONL outputs, computes each metric (below),
   normalizes each to 0–100, applies fixed weights, and prints + writes a
   verdict JSON: per-category winner, margin, and an overall weighted score.
   This is a deterministic, rerunnable script, not a one-off number typed into
   a doc — anyone (including a judge) can rerun it and get the same verdict from
   the same recorded data.
6. **`scripts/plot_architecture_comparison.py`** — renders the verdict JSON as
   figures into `docs/figures/`, matching `scripts/plot_model_comparison.py`'s
   existing style (matplotlib, Agg backend, the project's established color
   palette).
7. **`docs/24_Architecture_Comparison.md`** — the write-up: what each system is,
   methodology, results tables, the figures, the verdict, and — critically — a
   short "what Architecture B does that Architecture A doesn't" section (OCR, RAG,
   agentic multi-turn Q&A) called out honestly rather than buried, since a
   mentor will ask about it directly.

## Data & methodology

Both systems run against the same claim sample drawn from
`data/{development,validation,stress}/claims.jsonl` (600 claims, existing answer
key at `data/*/expected_results.jsonl`) — Architecture B already speaks this schema
(its committed `claim.csv` is verbatim one of Architecture A's own synthetic
examples, confirming compatibility). Sample size: start with the existing 36-case
set already used for prior model-comparison experiments (`docs/21_Experiments.md`)
for a fast first pass, then the full 600 if the local-model latency budget allows
(gemma3:4b's existing measured p95 is ~28s per call per docs/21 — Architecture B's
agent makes multiple tool-calling round-trips per claim, so this needs a real
timing check before committing to the full set; the harness supports `--sample-size`
so this is a runtime decision, not a design one).

## Metrics

Recorded per claim, aggregated per system:

- **Correctness**: status accuracy vs. answer key (reusing `src/evaluate.py`),
  false abstentions, missed abstentions. Architecture B's `overall_status` values
  (`VALID`/`REVIEW_REQUIRED`/`INVALID`/`INCOMPLETE`) get mapped to Architecture A's
  PASS/FAIL/UNABLE_TO_ASSESS shape for comparison — this mapping is written down
  explicitly in the doc, since it's the one place a judgment call is unavoidable.
- **Rapidness**: p50/p95 wall-clock latency per claim.
- **Efficiency**: tokens per claim (where the provider reports it), install
  footprint (dependency count/size), cold-start time (FAISS index build +
  embedding-model load vs. Architecture A's YARA-X rule-pack compile).
- **Security**: run a Architecture B-targeted variant of
  `tests/test_security_owasp.py`'s checks — dangerous-sink scan (the `eval()`
  calculator is a known candidate finding, though its regex prefilter limits
  real risk), prompt-injection resistance (reuse existing hostile-input fixtures
  from `tests/test_stress_ai_boundary.py` against Architecture B's agent), and
  citation/grounding checks (Architecture B has no equivalent to Architecture A's
  `check_grounding`/`_UNGROUNDED` guard — expected finding, not prejudged).
- **Deliverability**: a plain checklist, not a score alone — audit log, test
  suite, CI, auth/RBAC, offline capability, deployability, documentation. Stated
  as facts (has/doesn't have), with the score derived mechanically from the
  checklist so it isn't a subjective number pulled from nowhere.

## "Who wins" benchmark scoring

Weights (100 pts total), chosen to track the mentor's own stated evaluation
priorities where they overlap (`docs/07_Evaluation_and_Acceptance.md`:
correctness 35, security 15, audit/reproducibility 10) and extended with the
two axes the mentor separately asked for (rapidness, efficiency) that weren't
part of the original single-submission judging rubric:

| Category | Weight | Rationale |
|---|---|---|
| Correctness | 30 | Mirrors the mentor's own heaviest-weighted category. |
| Security | 20 | Mentor explicitly separated "uncertainty and security"; a RAG+agent system with no grounding guard is a real, checkable gap. |
| Deliverability | 20 | Mentor's point 7 ("near-production-ready, not a POC") makes this load-bearing, not cosmetic. |
| Rapidness | 15 | User-requested axis; matters for a real reviewer workflow. |
| Efficiency | 15 | User-requested axis; resource/dependency footprint matters for the mentor's point 8 (fully on-prem deployment). |

Each category's raw metric is normalized to 0–100 (method stated per-category in
the doc — e.g. correctness is just % accuracy; latency is normalized against the
slower of the two systems so the faster one scores 100), weighted, and summed.
The script reports the winner per category AND the overall weighted winner,
explicitly allowing a split verdict (e.g. Architecture B could win rapidness while
losing overall) rather than forcing one number to hide the nuance — that
nuance is exactly what a mentor's follow-up questions will probe.

## Testing / validation

- `scripts/score_architecture_comparison.py` gets its own unit tests (deterministic
  given fixed input JSONL — no live model calls in the test) verifying the
  normalization and weighting math, so the "who wins" number is provably not a
  typo.
- The comparison run itself is not part of Architecture A's own CI (it needs a local
  Ollama instance and Architecture B's extra dependencies) — it's a standalone,
  manually-triggered script, documented as such.

## Risks / open questions

- Architecture B's agent may be materially slower per claim (multiple tool-calling
  round-trips vs. Architecture A's single explanation call) — the full 600-claim run
  may not be practical locally; the doc will state whatever sample size was
  actually run and why.
- Architecture B has no committed way to run without a live LLM (no deterministic
  fallback), so a gemma3/Ollama outage mid-run fails that claim outright, not
  gracefully — this itself is a legitimate "deliverability" finding, not a bug
  in the harness.
- The correctness status-mapping (Architecture B's 4 statuses → Architecture A's 3) is a
  judgment call; stated explicitly rather than hidden in code.
