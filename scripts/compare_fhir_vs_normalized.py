"""Quantify what the FHIR ingestion path loses. For every claim in every public split:
(1) do all FHIR-carried fields equal the normalized claim, and (2) does each rule reach the
same status from the FHIR-derived claim as from the full normalized claim? Any case where the
FHIR path says PASS but the full data does not is a silent-pass defect and is counted separately.
Writes outputs/fhir_vs_normalized.json."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config, load_jsonl
from fhir_adapter import bundle_to_claim
from yara_engine import evaluate


def main():
    cfg = config(ROOT)
    agree, transitions, silent_pass, claims_n = Counter(), Counter(), [], 0
    for split in ('development', 'validation', 'stress'):
        normalized = {c['claim_id']: c for c in load_jsonl(ROOT / f'data/{split}/claims.jsonl')}
        for bundle in load_jsonl(ROOT / f'data/{split}/fhir_bundles.jsonl'):
            claim, _ = bundle_to_claim(bundle)
            claims_n += 1
            full = {r['rule_id']: r['status'] for r in evaluate(normalized[claim['claim_id']], cfg)}
            fhir = {r['rule_id']: r['status'] for r in evaluate(claim, cfg)}
            for rid, status in full.items():
                if status == fhir[rid]:
                    agree[rid] += 1
                else:
                    transitions[f'{rid}: {status} -> {fhir[rid]}'] += 1
                    if fhir[rid] == 'PASS':
                        silent_pass.append([split, claim['claim_id'], rid])
    report = {
        'claims': claims_n, 'results': claims_n * 15,
        'rules_with_identical_status_on_every_claim': sorted(r for r, n in agree.items() if n == claims_n),
        'status_agreement_per_rule': dict(sorted(agree.items())),
        'differences': dict(sorted(transitions.items())),
        'silent_passes_where_full_data_is_not_pass': silent_pass,
        'interpretation': 'FHIR bundles do not carry authorization details (docs/11); rules that need them '
                          'must degrade to UNABLE_TO_ASSESS, never PASS.',
    }
    out = ROOT / 'outputs/fhir_vs_normalized.json'
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('claims', 'differences', 'silent_passes_where_full_data_is_not_pass')}, indent=2))


if __name__ == '__main__':
    main()
