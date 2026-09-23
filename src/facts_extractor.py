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


def r003_details(c):
    cv = c['coverage']
    start = valid_date(cv['start_date'])
    end = valid_date(cv['end_date'])
    paths = ['/coverage/status', '/coverage/start_date', '/coverage/end_date']
    failed = []
    unknown = []
    facts = []
    ids = []
    if empty(cv['status']):
        unknown.append('coverage status')
    elif cv['status'] != 'active':
        failed.append('coverage status is not active')
        facts.append(f'R003:INACTIVE:status={cv["status"]}')
    if not start or not end:
        unknown.append('coverage period')
    for i, l in enumerate(c['lines']):
        paths.append(f'/lines/{i}/service_date')
        d = valid_date(l['service_date'])
        if not d:
            unknown.append('service date')
            continue
        if (start and d < start) or (end and d > end):
            failed.append('service outside coverage period')
            ids.append(l['line_id'])
            facts.append(
                f'R003:OUT_OF_PERIOD:/lines/{i}/service_date:service={d.isoformat()}:'
                f'start={start.isoformat() if start else ""}:end={end.isoformat() if end else ""}'
            )
    if failed:
        message = '; '.join(sorted(set(failed))) + (
            '; Additional unknown inputs: ' + ', '.join(sorted(set(unknown))) if unknown else ''
        )
    elif unknown:
        facts = ['R003:UNKNOWN']
        message = '; '.join(sorted(set(unknown)))
    else:
        facts = ['R003:OK']
        message = 'All service dates are within active coverage, including boundaries.'
    return {'facts': facts, 'evidence_paths': paths, 'line_ids': ids, 'message': message}
