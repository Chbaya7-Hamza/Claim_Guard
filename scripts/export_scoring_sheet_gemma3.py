"""Export a manual-scoring sheet for gemma3:4b's answers on the 36 cases originally prepared for the
Mistral-Nemo backlog (experiments/manual_scoring_sheet_e8/e9b/e10b.csv -- FX-*, FZ-*, FW-*, 12 cases each,
never actually scored). Those sheets hid which prompt/model "arm" answered each case, because the point was
comparing arms; that reason doesn't apply here since only one model is being scored, so this sheet skips the
blind key entirely and shows the case_id directly. Case order is still shuffled to avoid a round-order effect.

    python scripts/export_scoring_sheet_gemma3.py --seed 11

Writes experiments/manual_scoring_sheet_gemma3_rescore.csv. Scores are entered by hand; nothing here scores
anything -- see docs/07's 0/1 rubric (correct finding, correct evidence, correct rule, appropriate action,
honest uncertainty).
"""
import argparse
import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUBRIC = ['correct_finding', 'correct_evidence', 'correct_rule', 'appropriate_action', 'honest_uncertainty']
ROUNDS = ['fresh2', 'fresh3', 'fresh4']  # FX, FZ, FW -- the 3 rounds prepared for e8/e9b/e10b


def load_cases():
    cases = {}
    for r in ROUNDS:
        for line in (ROOT / 'exercises' / f'{r}_variants.jsonl').read_text(encoding='utf-8').splitlines():
            if line.strip():
                c = json.loads(line)
                cases[c['case_id']] = c
    return cases


def load_answers():
    answers = {}
    for r in ROUNDS:
        for line in (ROOT / 'outputs' / f'llm_explanations_gemma3_{r}.jsonl').read_text(encoding='utf-8').splitlines():
            if line.strip():
                rec = json.loads(line)
                answers[rec['case_id']] = rec
    return answers


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--seed', type=int, default=11)
    a = p.parse_args()

    cases = load_cases()
    answers = load_answers()
    missing = set(cases) - set(answers)
    if missing:
        raise SystemExit(f'No gemma3 answer recorded for: {sorted(missing)} -- run scripts/run_llm_explanations.py first')

    rng = random.Random(a.seed)
    ids = list(cases)
    rng.shuffle(ids)

    out = ROOT / 'experiments' / 'manual_scoring_sheet_gemma3_rescore.csv'
    with out.open('w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['item', 'case_id', 'rule_id', 'status', 'engine_explanation', 'evidence', 'corrective_action',
                     'model', 'used_fallback', 'answer'] + RUBRIC + ['unsupported_facts', 'notes'])
        for n, cid in enumerate(ids, start=1):
            case = cases[cid]
            rec = answers[cid]
            f = case['finding']
            evidence = '; '.join(f"{e['path']} = {json.dumps(e['value'], ensure_ascii=False)}" for e in f['evidence'])
            answer_text = rec['output']['explanation'] if not rec['used_fallback'] else '(fell back to template -- nothing to score)'
            w.writerow([f'G{n:03d}', cid, f['rule_id'], f['status'], f['explanation'], evidence,
                        case['rule']['corrective_action'], rec.get('model') or 'gemma3:4b', rec['used_fallback'],
                        answer_text] + [''] * (len(RUBRIC) + 2))
    print(f'{len(ids)} answers (gemma3:4b, cases originally prepared for e8/e9b/e10b) -> {out}')


if __name__ == '__main__':
    main()
