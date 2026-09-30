# ClaimGuard vs. clinicProj architecture comparison

Source: `comparison/clinicproj-src/` is a frozen, unmodified copy of
`https://github.com/ayechiahmed/clinicProj`, commit `3249ecb` ("Initial
commit"), cloned 2026-09-28. It exists so this comparison is reproducible
without depending on the external repo staying available — it is reference
material, never edited.

`comparison/clinicproj_adapted/` is a working copy of only the files that
repo's code actually imports (`agent.py`, `extractor.py`,
`document_loader.py`, `policies/`), with exactly one change: the LLM binding
is swapped from cloud Gemini to the same local gemma3:4b (via Ollama) that
ClaimGuard's own `src/llm_adapter.py` already uses, so the comparison is
about architecture, not which cloud API key someone had. No other logic is
changed — same LangGraph ReAct agent, same system prompt, same RAG, same OCR
path.

Full design: `docs/superpowers/specs/2026-09-28-clinicproj-architecture-comparison-design.md`
Results and verdict: `docs/24_Architecture_Comparison.md`

## Two runs, two models

1. `gemma3-4b-ollama` (original, offline): clinicProj could not run at all because gemma3:4b has no tool-calling. Results are
   kept in `outputs/architecture_comparison/gemma3-4b-ollama/`.
2. `qwen25-14b-featherless` (hosted, tool-capable): both systems on `Qwen/Qwen2.5-14B-Instruct` through Featherless. Why this model:
   `docs/25_Comparison_Model_Selection.md`. Needs `FEATHERLESS_API_KEY` in `.env`. Run the systems **one after another**, never
   in parallel (Featherless returns "No successful response" errors under contention).

    comparison/.venv/Scripts/python scripts/run_clinicproj_comparison.py --sample-size 12 --system clinicproj --provider featherless --model Qwen/Qwen2.5-14B-Instruct --tag qwen25-14b-featherless
    .venv/Scripts/python scripts/run_clinicproj_comparison.py --sample-size 12 --system claimguard --provider featherless --model Qwen/Qwen2.5-14B-Instruct --tag qwen25-14b-featherless
    comparison/.venv/Scripts/python scripts/security_scan_clinicproj.py --live --provider featherless --model Qwen/Qwen2.5-14B-Instruct --tag qwen25-14b-featherless
    .venv/Scripts/python scripts/score_clinicproj_comparison.py --tag qwen25-14b-featherless --hallucination            # strict (default)
    .venv/Scripts/python scripts/score_clinicproj_comparison.py --tag qwen25-14b-featherless --hallucination --lenient # JSON wrapped in prose/fences accepted

Both scorings are reported. Strict is the default because clinicProj has no parser of its own; lenient is a disclosed
adjustment for a formatting habit of the model, not a change to clinicProj's logic. The `hallucination` category rebalances
the weights (correctness 25, hallucination 15, security 20, deliverability 15, rapidness 15, efficiency 10).

## Running the comparison yourself (original gemma3 run)

clinicProj's dependencies (`langchain`, `langgraph`, `faiss-cpu`,
`sentence-transformers`) are NOT part of ClaimGuard's own `requirements.txt`
and are not installed by ClaimGuard's CI. To run this comparison locally:

    python -m venv comparison/.venv
    comparison/.venv/Scripts/pip install -r comparison/clinicproj_adapted/requirements.txt -r comparison/clinicproj_adapted/requirements-harness.txt
    ollama pull gemma3:4b   # if not already pulled
    ollama serve            # if not already running

    # clinicProj-specific unit tests (need the venv above):
    comparison/.venv/Scripts/python -m unittest discover -s comparison/clinicproj_adapted/tests

    # the actual comparison run (needs Ollama running, ~minutes per claim).
    # ClaimGuard's own deps (yara-x, openai==3.19.0) and clinicProj's
    # (langchain-openai, which needs openai<2.0.0) genuinely conflict in one
    # venv -- run each system with its own venv, not `--system both`:
    .venv/Scripts/python scripts/run_clinicproj_comparison.py --sample-size 36 --system claimguard
    comparison/.venv/Scripts/python scripts/run_clinicproj_comparison.py --sample-size 36 --system clinicproj

    # security scan needs clinicProj's own deps too (it builds the same agent):
    comparison/.venv/Scripts/python scripts/security_scan_clinicproj.py --live

    # scoring is pure stdlib -- ClaimGuard's own venv is fine:
    .venv/Scripts/python scripts/score_clinicproj_comparison.py

    # plotting needs matplotlib, which is bundled into comparison/.venv, not
    # ClaimGuard's own requirements.txt (see comparison/clinicproj_adapted/requirements.txt):
    comparison/.venv/Scripts/python scripts/plot_clinicproj_comparison.py
