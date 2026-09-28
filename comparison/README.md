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

## Running the comparison yourself

clinicProj's dependencies (`langchain`, `langgraph`, `faiss-cpu`,
`sentence-transformers`) are NOT part of ClaimGuard's own `requirements.txt`
and are not installed by ClaimGuard's CI. To run this comparison locally:

    python -m venv comparison/.venv
    comparison/.venv/Scripts/pip install -r comparison/clinicproj_adapted/requirements.txt
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
