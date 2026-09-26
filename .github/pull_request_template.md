## What and why

<!-- One or two sentences. Link the rule, doc or issue if there is one. -->

## Checklist

- [ ] `python -m unittest discover -s tests` passes locally (offline, no API key)
- [ ] I did not commit `.env`, a key or a token
- [ ] I did not edit `SHA256SUMS.json`
- [ ] A rule change touches `rules/core.yar` **and** `src/facts_extractor.py` together, with a test in `tests/test_stress_boundaries.py`
- [ ] A PASS is never described as an approval, in code or docs
- [ ] Docs updated if behaviour changed (`README.md`, `SPECS.md`, `docs/`)
