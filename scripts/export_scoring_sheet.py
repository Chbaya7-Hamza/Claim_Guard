"""Export a blind manual-scoring sheet from recorded experiment answers.

A person scores each answer with the 0/1 rubric of docs/07 (correct finding, correct evidence, correct rule, appropriate
action, honest uncertainty) and lists unsupported facts. The sheet shows the case, the engine's finding, the evidence and the
answer, in shuffled order, with the arm hidden. The key that maps an item back to its arm is written to a separate file that
the scorer must not open until the sheet is finished.

    python scripts/export_scoring_sheet.py --experiment e8 --per-arm 50 --seed 7

Writes experiments/manual_scoring_sheet_<experiment>.csv and experiments/manual_scoring_key_<experiment>.csv. Scores are entered by hand; nothing here
scores anything.
"""
import argparse
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from run_experiments import load_cases

RUBRIC = ['correct_finding', 'correct_evidence', 'correct_rule', 'appropriate_action', 'honest_uncertainty']


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--experiment', default='e8')
    p.add_argument('--per-arm', type=int, default=50)
    p.add_argument('--seed', type=int, default=7)
    a = p.parse_args()
    cases = {c['case_id']: c for which in ('tuning', 'fresh', 'fresh2', 'fresh3') for c in load_cases(which)}
    calls = [json.loads(l) for l in (ROOT / 'experiments' / 'raw' / f'{a.experiment}.jsonl').read_text(encoding='utf-8').split(chr(10))
             if l.strip()]
    calls = [r for r in calls if r['type'] == 'call' and r['outcome'] == 'live']
    rng = random.Random(a.seed)
    picked = []
    for arm in sorted({r['cfg_id'] for r in calls}):
        rows = [r for r in calls if r['cfg_id'] == arm]
        rng.shuffle(rows)
        picked += rows[:a.per_arm]
    rng.shuffle(picked)
    sheet = ROOT / 'experiments' / f'manual_scoring_sheet_{a.experiment}.csv'
    key = ROOT / 'experiments' / f'manual_scoring_key_{a.experiment}.csv'
    with sheet.open('w', newline='', encoding='utf-8') as fs, key.open('w', newline='', encoding='utf-8') as fk:
        ws = csv.writer(fs)
        wk = csv.writer(fk)
        ws.writerow(['item', 'case_id', 'rule_id', 'status', 'engine_explanation', 'evidence', 'corrective_action', 'answer']
                    + RUBRIC + ['unsupported_facts', 'notes'])
        wk.writerow(['item', 'arm', 'answered_by', 'experiment', 'repeat'])
        for n, r in enumerate(picked, start=1):
            case = cases[r['case_id']]
            f = case['finding']
            evidence = '; '.join(f"{e['path']} = {json.dumps(e['value'], ensure_ascii=False)}" for e in f['evidence'])
            ws.writerow([f'S{n:03d}', r['case_id'], f['rule_id'], f['status'], f['explanation'], evidence,
                         case['rule']['corrective_action'], r['explanation']] + [''] * (len(RUBRIC) + 2))
            wk.writerow([f'S{n:03d}', r['cfg_id'], r.get('answered_by') or '', a.experiment, r['rep']])
    print(f'{len(picked)} answers -> {sheet} (key: {key}, do not open until scoring is done)')


if __name__ == '__main__':
    main()
