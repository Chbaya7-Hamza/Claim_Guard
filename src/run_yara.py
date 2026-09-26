"""Run the full YARA-X facts-blob rule pack (all 15 rules) over claims.

Never loses claims silently and never aborts the batch for one bad claim:
  - a malformed JSON line is skipped and reported (there is no claim id to attach results to);
  - a claim that fails the transport contract but has a claim_id gets 15 fail-closed
    UNABLE_TO_ASSESS results (never PASS), so the output still covers every identifiable claim;
  - an unexpected error inside one rule is isolated to that rule (see yara_engine.evaluate).
The exit code is 2 when anything above happened, and the summary says exactly what.
EngineError (rule pack and extractor out of sync) is a build defect and still aborts.
"""
import argparse
import json
import sys
from pathlib import Path

from engine_core import config, validate_transport
from jsonl_reader import parse_json, read_lines
from yara_engine import evaluate, fail_closed_results


def run(input_path, output_path, cfg, limit=None):
    summary = {'claims': 0, 'results': 0, 'fail_closed_claims': [], 'unreadable_lines': [], 'tool_errors': []}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', encoding='utf-8') as f:
        for n, line, read_error in read_lines(input_path):
            if limit is not None and summary['claims'] >= limit:
                break
            if read_error:
                summary['unreadable_lines'].append({'line': n, 'error': read_error})
                continue
            c, parse_error = parse_json(line)
            if parse_error:
                summary['unreadable_lines'].append({'line': n, 'error': parse_error})
                continue
            summary['claims'] += 1
            errors = []
            try:
                validate_transport(c)
                results = evaluate(c, cfg, errors)
            except (ValueError, KeyError, TypeError) as e:
                reason = f'{type(e).__name__}: {e}'
                if isinstance(c, dict) and isinstance(c.get('claim_id'), str) and c['claim_id']:
                    results = fail_closed_results(c, cfg)
                    summary['fail_closed_claims'].append({'line': n, 'claim_id': c['claim_id'], 'reason': reason})
                else:
                    summary['unreadable_lines'].append({'line': n, 'error': f'no usable claim_id ({reason})'})
                    continue
            summary['tool_errors'].extend(f"{c['claim_id']}: {e}" for e in errors)
            for r in results:
                f.write(json.dumps(r) + '\n')  # ASCII-escaped: U+2028 and friends can never split a record
            summary['results'] += len(results)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--input', default='data/development/claims.jsonl')
    p.add_argument('--output', default='outputs/yara_predictions.jsonl')
    p.add_argument('--limit', type=int)
    a = p.parse_args()
    cfg = config(Path(__file__).resolve().parents[1])
    s = run(a.input, a.output, cfg, a.limit)
    print(f'Processed {s["claims"]} claims across {len(cfg["rules"])} rules (R001-R015): {s["results"]} results. Output: {a.output}')
    problems = bool(s['fail_closed_claims'] or s['unreadable_lines'] or s['tool_errors'])
    if problems:
        print(f'WARNING: {len(s["fail_closed_claims"])} claim(s) failed transport and were emitted as fail-closed '
              f'UNABLE_TO_ASSESS; {len(s["unreadable_lines"])} line(s) unreadable and skipped; '
              f'{len(s["tool_errors"])} isolated rule error(s).', file=sys.stderr)
        for k in ('fail_closed_claims', 'unreadable_lines', 'tool_errors'):
            for item in s[k][:20]:
                print(f'  {k}: {item}', file=sys.stderr)
    sys.exit(2 if problems else 0)


if __name__ == '__main__':
    main()
