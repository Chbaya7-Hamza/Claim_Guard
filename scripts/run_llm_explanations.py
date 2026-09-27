"""Run the Featherless-backed ExplanationProvider (with deterministic fallback)
over the 25 supplied bounded-AI exercise cases in
exercises/llm_explanation_cases.jsonl, and produce:

- outputs/llm_explanations.jsonl -- one record per case: the raw explanation
  output, whether it came from the model or the fallback, the error (if any),
  and latency.
- outputs/llm_manual_scorecard.csv -- a copy of the supplied blank scorecard
  template, pre-filled with latency_ms and an auto-note on fallback/errors,
  ready for a human reviewer to fill in the qualitative 0/1 columns
  (correct_finding, correct_evidence, correct_rule, appropriate_action,
  honest_uncertainty) per docs/05 and docs/07's AI evaluation protocol.
"""
import argparse
import csv
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from llm_adapter import (FeatherlessExplanationProvider, MedGemmaExplanationProvider, MockExplanationProvider,
                          OllamaExplanationProvider, explain_with_fallback)

logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(name)s: %(message)s')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', default='exercises/llm_explanation_cases.jsonl')
    ap.add_argument('--output', default='outputs/llm_explanations.jsonl')
    ap.add_argument('--no-scorecard', action='store_true', help='skip the manual scorecard (only valid for the 25 supplied cases)')
    ap.add_argument('--workers', type=int, default=1, help='cases explained concurrently')
    ap.add_argument('--provider', choices=('featherless', 'ollama', 'medgemma'), default='featherless')
    ap.add_argument('--model', default=None, help='overrides the provider default model')
    ap.add_argument('--max-tokens', type=int, default=500)
    args = ap.parse_args()
    cases = [json.loads(l) for l in (ROOT / args.cases).read_text(encoding='utf-8').splitlines() if l.strip()]

    provider_cls = {'ollama': OllamaExplanationProvider, 'medgemma': MedGemmaExplanationProvider,
                     'featherless': FeatherlessExplanationProvider}[args.provider]
    try:
        primary = provider_cls(model=args.model, max_tokens=args.max_tokens)
        print(f'Primary provider: {args.provider} ({primary.model})')
    except Exception as e:
        primary = None
        print(f'No live provider available ({e}); every case will use the mock fallback.')

    fallback = MockExplanationProvider()
    def one(case):
        finding, rule = case['finding'], case['rule']
        active_primary = primary or fallback
        output, used_fallback, error, latency_ms = explain_with_fallback(
            active_primary, fallback, finding, rule, case.get('untrusted_note'))
        live = not (used_fallback or primary is None)
        # usage/attempts are per-thread on the provider: read them here, in the worker
        return {
            'case_id': case['case_id'], 'task': case['task'],
            'output': output, 'used_fallback': not live,
            'error': error, 'latency_ms': round(latency_ms, 1),
            'model': getattr(primary, 'model', None),
            'attempts': getattr(primary, 'last_attempts', None) if live else None,
            'usage': getattr(primary, 'last_usage', None) if live else None,
        }

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        results = list(pool.map(one, cases))
    for r in results:
        print(f"{r['case_id']} [{'FALLBACK' if r['used_fallback'] else 'MODEL'}] {round(r['latency_ms'])}ms"
              + (f" -- {r['error']}" if r['error'] else ''))
    print(f'Wall time {time.monotonic() - t0:.1f}s with {args.workers} worker(s)')

    out_path = ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open('w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    if args.no_scorecard:
        n_fallback = sum(1 for r in results if r['used_fallback'])
        print(f'\n{len(results)} cases; {len(results) - n_fallback} answered by the model, {n_fallback} fell back.')
        print(f'Explanations: {out_path}')
        return

    template_rows = list(csv.DictReader((ROOT / 'exercises/llm_manual_scorecard.csv').open(encoding='utf-8')))
    by_case = {r['case_id']: r for r in results}
    for row in template_rows:
        r = by_case.get(row['case_id'])
        if not r:
            continue
        row['latency_ms'] = r['latency_ms']
        if r['error']:
            row['reviewer_notes'] = f"AUTO: fell back to mock ({r['error']})"
        elif r['used_fallback']:
            row['reviewer_notes'] = 'AUTO: no live provider configured; used mock'

    scorecard_path = ROOT / 'outputs/llm_manual_scorecard.csv'
    with scorecard_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(csv.DictReader(open(ROOT / 'exercises/llm_manual_scorecard.csv', encoding='utf-8')).fieldnames))
        writer.writeheader()
        writer.writerows(template_rows)

    n_fallback = sum(1 for r in results if r['used_fallback'])
    print(f'\n{len(results)} cases; {len(results) - n_fallback} answered by the model, {n_fallback} fell back to the deterministic template.')
    print(f'Explanations: {out_path}')
    print(f'Scorecard (fill in the qualitative columns): {scorecard_path}')


if __name__ == '__main__':
    main()
