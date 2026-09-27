"""Stress-test a local (Ollama) model the same way docs/21's experiments stress-tested the hosted candidates:
volume, garbled-raw-reply rate independent of whether the safety net caught it, and repeat-call consistency
at temperature 0 (a hosted-model finding was "not word-for-word deterministic even at temperature 0" --
worth checking whether that holds for a locally-served GGUF model too).

    python scripts/stress_test_local_model.py --model gemma3:4b [--repeats 10]

Cases: every exercise case file (25 supplied + 11 own injection variants + 4 x 12 "fresh" confirmation
sets = 84 total), each run once; plus `--repeats` of them re-run 3x each at the same temperature to check
for call-to-call drift. Writes outputs/stress_<model>.json.
"""
import argparse
import copy
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from llm_adapter import OllamaExplanationProvider, MockExplanationProvider, explain_with_fallback, _FOREIGN_SCRIPT, _REPETITION  # noqa: E402

CASE_FILES = ['llm_explanation_cases.jsonl', 'injection_variants.jsonl',
              'fresh_variants.jsonl', 'fresh2_variants.jsonl', 'fresh3_variants.jsonl', 'fresh4_variants.jsonl']


class RecordingOllamaProvider(OllamaExplanationProvider):
    """Keeps the raw reply text of every call this thread makes, rejected or not, for garbled-text analysis."""
    def _complete(self, prompt):
        text = super()._complete(prompt)
        raws = getattr(self._tl, 'raws', None)
        if raws is not None:
            raws.append(text[:3000])
        return text


def load_all_cases():
    cases = []
    for name in CASE_FILES:
        for line in (ROOT / 'exercises' / name).read_text(encoding='utf-8').splitlines():
            if line.strip():
                cases.append(json.loads(line))
    return cases


def is_garbled(text):
    """Same signature docs/21 used to classify a raw reply as derailed: text in an unexpected script, or a
    long repetition -- checked directly against the raw reply, independent of whether check_grounding's
    stricter in-context check happened to also flag (or miss) it."""
    if _REPETITION.search(text):
        return 'long repetition'
    m = _FOREIGN_SCRIPT.search(text)
    if m:
        return f'unexpected script: {m.group(0)!r}'
    return None


def run_once(provider, fallback, case):
    provider._tl.raws = []
    t0 = time.monotonic()
    output, used_fallback, error, latency_ms = explain_with_fallback(
        provider, fallback, copy.deepcopy(case['finding']), copy.deepcopy(case['rule']), case.get('untrusted_note'))
    raws = list(getattr(provider._tl, 'raws', []))
    return {
        'case_id': case['case_id'], 'used_fallback': used_fallback, 'error': error,
        'latency_ms': round(latency_ms, 1), 'raw_replies': raws,
        'garbled': [is_garbled(r) for r in raws if is_garbled(r)],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--model', default='gemma3:4b')
    ap.add_argument('--repeats', type=int, default=10, help='how many of the 84 cases to also re-run 3x for a determinism check')
    a = ap.parse_args()

    cases = load_all_cases()
    print(f'Loaded {len(cases)} cases from {len(CASE_FILES)} files.')

    provider = RecordingOllamaProvider(model=a.model)
    fallback = MockExplanationProvider()

    print(f'\n--- Single pass over all {len(cases)} cases ---')
    single = []
    for i, c in enumerate(cases, 1):
        r = run_once(provider, fallback, c)
        single.append(r)
        flag = 'FALLBACK' if r['used_fallback'] else ('GARBLED' if r['garbled'] else 'ok')
        print(f"  [{i}/{len(cases)}] {r['case_id']}: {flag} ({round(r['latency_ms'])}ms)"
              + (f" -- {r['error']}" if r['error'] else '') + (f" -- {r['garbled']}" if r['garbled'] else ''))

    print(f'\n--- Determinism check: {a.repeats} cases re-run 3x each at the same settings ---')
    determinism = []
    for c in cases[:a.repeats]:
        runs = [run_once(provider, fallback, c) for _ in range(3)]
        texts = [r['raw_replies'][-1] if r['raw_replies'] else None for r in runs]
        identical = len(set(texts)) == 1
        determinism.append({'case_id': c['case_id'], 'identical_across_3_runs': identical,
                             'used_fallback': [r['used_fallback'] for r in runs],
                             'latency_ms': [r['latency_ms'] for r in runs]})
        print(f"  {c['case_id']}: identical_across_3_runs={identical}"
              + ('' if identical else f" -- texts differed"))

    n_live = sum(1 for r in single if not r['used_fallback'])
    n_garbled = sum(1 for r in single if r['garbled'])
    n_fallback = len(single) - n_live
    n_stable = sum(1 for d in determinism if d['identical_across_3_runs'])

    summary = {
        'model': a.model, 'cases': len(cases),
        'live': n_live, 'fallback': n_fallback, 'garbled_raw_replies': n_garbled,
        'fallback_errors': {r['case_id']: r['error'] for r in single if r['used_fallback']},
        'determinism_checked': len(determinism), 'determinism_stable': n_stable,
        'determinism_detail': determinism,
        'single_pass': single,
    }
    out = ROOT / 'outputs' / f'stress_{a.model.replace(":", "_").replace("/", "_")}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')

    print(f'\n=== Summary: {a.model} ===')
    print(f'  {n_live}/{len(cases)} live ({n_live/len(cases)*100:.1f}%), {n_fallback} fell back, {n_garbled} garbled raw replies (out of {len(cases)}).')
    print(f'  Determinism: {n_stable}/{len(determinism)} cases gave byte-identical output across 3 repeats at the same settings.')
    print(f'  Written: {out}')


if __name__ == '__main__':
    main()
