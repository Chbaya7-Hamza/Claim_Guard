"""Advisory checks: defects the 15 fictional rules do not look at.

The rulebook (docs/04) fixes the scored rule set, and its PASS only ever means "these 15 checks passed". A red-team run
showed two things a reviewer would want to know that no rule covers: a diagnosis code that is not in the supplied
teaching catalogue (rules/diagnoses.json), and a claim whose payer differs from the policy it names.

These are NOT rule results. They are never part of the scored output, never change a rule status, and never say a claim
is valid or invalid. They are recorded in the audit log as `advisory_check` events and route the claim to a human.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _diagnosis_codes():
    rows = json.loads((ROOT / 'rules' / 'diagnoses.json').read_text(encoding='utf-8'))
    return {r['code'] for r in rows}


def advisory_checks(claim, cfg):
    """[{'check_id', 'detail'}] for each advisory that fires on this claim; [] when none do."""
    out = []
    code = claim.get('diagnosis_code')
    if isinstance(code, str) and code.strip() and code not in _diagnosis_codes():
        out.append({'check_id': 'ADV-DIAGNOSIS-NOT-IN-CATALOGUE',
                    'detail': 'diagnosis_code is not in the supplied fictional catalogue (rules/diagnoses.json); '
                              'no rule checks this'})
    policy = cfg['policies'].get(claim.get('policy_id'))
    payer = claim.get('payer_id')
    if policy is not None and isinstance(payer, str) and payer != policy.get('payer_id'):
        out.append({'check_id': 'ADV-PAYER-POLICY-MISMATCH',
                    'detail': f'payer_id does not match the payer of policy {claim.get("policy_id")}; no rule checks this'})
    return out
