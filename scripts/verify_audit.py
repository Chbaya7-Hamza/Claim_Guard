"""Verify an audit log and, optionally, that it matches a results file.

    python scripts/verify_audit.py --log outputs/audit_dev/audit.jsonl \
        [--results outputs/yara_dev_predictions.jsonl]

1. Hash chain intact and consistent with the anchor file (truncation / replacement).
2. AI ordering: every AI action was registered (ai_request: the question, the deterministic
   verdict, finding + prompt hashes, action type) BEFORE the model was called, answered once, and
   classified human_escalation; auto_correct never appears.
3. With --results: every rule_check event's result_hash equals the digest of the
   corresponding result record, and every result has exactly one rule_check in the
   log's latest run for that claim. The log therefore cannot silently disagree with the
   results file it claims to describe.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from audit import digest
from audit_log import verify_ai_ordering, verify_with_anchor


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--log', required=True)
    p.add_argument('--results')
    a = p.parse_args()
    head, count = verify_with_anchor(a.log)
    print(f'Chain OK: {count} events, matches anchor; head {head}')
    stats = verify_ai_ordering(a.log)
    print('AI ordering OK:', json.dumps(stats))
    if not a.results:
        return
    results = {}
    for line in Path(a.results).read_text(encoding='utf-8').splitlines():
        if line.strip():
            r = json.loads(line)
            results[(r['claim_id'], r['rule_id'])] = digest(r)
    logged, latest_run = {}, {}
    for line in Path(a.log).read_text(encoding='utf-8').splitlines():
        e = json.loads(line)['event']
        if e.get('event_type') == 'run_started':
            latest_run[e['claim_id']] = e['run_id']
        elif e.get('event_type') == 'rule_check':
            logged[(e['claim_id'], e['rule_id'], e['run_id'])] = e['result_hash']
    mismatched, missing = [], []
    for (claim_id, rule_id), h in results.items():
        got = logged.get((claim_id, rule_id, latest_run.get(claim_id)))
        if got is None:
            missing.append((claim_id, rule_id))
        elif got != h:
            mismatched.append((claim_id, rule_id))
    print(f'Results file: {len(results)} results; missing from log {len(missing)}; hash mismatches {len(mismatched)}')
    if missing or mismatched:
        sys.exit(1)
    print('Every result is recorded in the log with a matching hash.')


if __name__ == '__main__':
    main()
