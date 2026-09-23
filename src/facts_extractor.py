"""Deterministic fact extraction for the YARA facts-blob harness (R001/R003/R006).

Each rXXX_details(claim) is the single source of truth for that rule: it
computes the fact-tag lines YARA will pattern-match on, the evidence paths
and line ids the assembled result reports, and the human-readable message —
all from one pass over the claim, so the three can never drift apart.
"""
from engine_core import empty, valid_date


def r001_details(c):
    paths = []
    ids = []
    for k in ('invoice_number', 'member_id', 'diagnosis_code'):
        if empty(c[k]):
            paths.append(f'/{k}')
    for i, l in enumerate(c['lines']):
        for k in ('service_date', 'service_code', 'quantity', 'unit_price', 'net_amount'):
            if empty(l[k]):
                paths.append(f'/lines/{i}/{k}')
                ids.append(l['line_id'])
    if paths:
        return {
            'facts': [f'R001:MISSING:{p}' for p in paths],
            'evidence_paths': list(dict.fromkeys(paths)),
            'line_ids': sorted(set(ids)),
            'message': 'Required information is missing.',
        }
    return {
        'facts': ['R001:OK'],
        'evidence_paths': ['/invoice_number', '/member_id', '/diagnosis_code', '/lines'],
        'line_ids': [],
        'message': 'Required information is present.',
    }
