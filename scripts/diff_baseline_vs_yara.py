"""Throwaway equivalence proof: yara_engine must reproduce engine_core.baseline
for R001/R003/R006 over the full development split, field-for-field."""
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config, load_jsonl, base_check, validate_transport
from yara_engine import evaluate

SCOPE = ('R001', 'R003', 'R006')


def main():
    cfg = config(ROOT)
    claims = load_jsonl(ROOT / 'data/development/claims.jsonl')
    rule_defs = {r['rule_id']: r for r in cfg['rules']}
    mismatches = []
    for c in claims:
        validate_transport(c)
        old = {rid: base_check(c, rule_defs[rid]) for rid in SCOPE}
        new = {r['rule_id']: r for r in evaluate(c, cfg)}
        for rid in SCOPE:
            if old[rid] != new[rid]:
                mismatches.append((c['claim_id'], rid, old[rid], new[rid]))
    if mismatches:
        for claim_id, rid, old_r, new_r in mismatches[:5]:
            print(f'MISMATCH {claim_id} {rid}')
            print('  baseline:', json.dumps(old_r, sort_keys=True))
            print('  yara    :', json.dumps(new_r, sort_keys=True))
        print(f'{len(mismatches)} mismatches out of {len(claims) * len(SCOPE)} rule results')
        sys.exit(1)
    print(f'MATCH: {len(claims)} claims x {len(SCOPE)} rules, '
          f'{len(claims) * len(SCOPE)} results identical to the existing baseline.')


if __name__ == '__main__':
    main()
