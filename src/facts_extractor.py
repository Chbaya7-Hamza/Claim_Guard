"""Deterministic fact extraction for the YARA facts-blob harness (R001-R015).

Each rXXX_details(claim[, cfg]) is the single source of truth for that rule: it
computes the fact-tag lines YARA will pattern-match on, the evidence paths
and line ids the assembled result reports, and the human-readable message —
all from one pass over the claim, so the tags YARA sees and the result fields
assembled afterward can never drift apart. yara_engine.evaluate() builds the
combined facts blob directly from these functions' output.
"""
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext

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


def r006_details(c):
    seen = {}
    dups = []
    missing = False
    facts = []
    for i, l in enumerate(c['lines']):
        if empty(l['service_code']) or not valid_date(l['service_date']):
            missing = True
            continue
        key = (l['service_code'], l['service_date'], l['modifier'] or '')
        if key in seen:
            a = seen[key]
            dups.extend([a, i])
            facts.append(f'R006:DUPLICATE:{a},{i}:key={"|".join(key)}')
        else:
            seen[key] = i
    ids = []
    paths = []
    for i in sorted(set(dups)):
        ids.append(c['lines'][i]['line_id'])
        paths.extend(f'/lines/{i}/{k}' for k in ('service_code', 'service_date', 'modifier'))
    if dups:
        message = 'Possible duplicate lines require review.' + (
            ' Additional lines have missing inputs.' if missing else ''
        )
    elif missing:
        facts = ['R006:UNKNOWN']
        message = 'Missing inputs prevent a complete duplicate check.'
    else:
        facts = ['R006:OK']
        message = 'No duplicate service/date/modifier combinations.'
    return {'facts': facts, 'evidence_paths': paths or ['/lines'], 'line_ids': ids, 'message': message}


def r002_details(c):
    sub = valid_date(c['submission_date'])
    paths = ['/submission_date']
    unknown = []
    facts = []
    ids = []
    if not sub:
        unknown.append('submission date')
    for i, l in enumerate(c['lines']):
        paths.append(f'/lines/{i}/service_date')
        d = valid_date(l['service_date'])
        if not d:
            unknown.append('service date')
            continue
        if sub and d > sub:
            ids.append(l['line_id'])
            facts.append(f'R002:LATE:/lines/{i}/service_date:service={d.isoformat()}:submission={sub.isoformat()}')
    if facts:
        message = 'Service date is after the submission date.' + (
            ' Additional unknown inputs: ' + ', '.join(sorted(set(unknown))) if unknown else ''
        )
    elif unknown:
        facts = ['R002:UNKNOWN']
        message = '; '.join(sorted(set(unknown)))
    else:
        facts = ['R002:OK']
        message = 'All service dates are on or before the submission date.'
    return {'facts': facts, 'evidence_paths': paths, 'line_ids': ids, 'message': message}


def r004_details(c):
    pid, bpid = c['patient_id'], c['coverage']['beneficiary_patient_id']
    mid, cmid = c['member_id'], c['coverage']['member_id']
    paths = ['/patient_id', '/coverage/beneficiary_patient_id', '/member_id', '/coverage/member_id']
    unknown = []
    mismatches = []
    if empty(pid) or empty(bpid):
        unknown.append('patient identifiers')
    elif pid != bpid:
        mismatches.append(f'R004:PATIENT_MISMATCH:patient_id={pid}:beneficiary_patient_id={bpid}')
    if empty(mid) or empty(cmid):
        unknown.append('member identifiers')
    elif mid != cmid:
        mismatches.append(f'R004:MEMBER_MISMATCH:member_id={mid}:coverage_member_id={cmid}')
    if mismatches:
        facts = mismatches
        message = 'Patient or member identifiers do not match coverage.'
    elif unknown:
        facts = ['R004:UNKNOWN']
        message = '; '.join(sorted(set(unknown)))
    else:
        facts = ['R004:OK']
        message = 'Patient and member identifiers match coverage.'
    return {'facts': facts, 'evidence_paths': paths, 'line_ids': [], 'message': message}


def r005_details(c, cfg):
    pid = c['provider_id']
    policy = cfg['policies'].get(c['policy_id'])
    paths = ['/provider_id', '/policy_id']
    if empty(pid) or policy is None:
        facts = ['R005:UNKNOWN']
        message = 'Provider or policy is unknown.'
    elif pid not in policy['allowed_providers']:
        facts = [f'R005:UNLISTED:provider_id={pid}']
        message = 'Provider is not in the allowed network.'
    else:
        facts = ['R005:OK']
        message = 'Provider is in the allowed network.'
    return {'facts': facts, 'evidence_paths': paths, 'line_ids': [], 'message': message}


# Money is compared exactly: the submitted amount is not rounded before the 0.01 tolerance is applied
# (docs/04: "Do not silently trim or repair source data"), and the context is wide enough that an
# absurdly large but valid number is a FAIL rather than a decimal overflow.
_WIDE = Context(prec=5000, rounding=ROUND_HALF_UP, Emax=999999, Emin=-999999)


def r007_details(c):
    paths = []
    unknown = []
    facts = []
    ids = []
    for i, l in enumerate(c['lines']):
        paths.extend([f'/lines/{i}/quantity', f'/lines/{i}/unit_price', f'/lines/{i}/net_amount'])
        q, u, n = l['quantity'], l['unit_price'], l['net_amount']
        if q is None or u is None or n is None:
            unknown.append('line amount inputs')
            continue
        with localcontext(_WIDE):
            expected = (Decimal(str(q)) * Decimal(str(u))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            actual = Decimal(str(n))
            off = abs(expected - actual) > Decimal('0.01')
        if off:
            ids.append(l['line_id'])
            facts.append(f'R007:MISMATCH:/lines/{i}/net_amount:expected={expected}:actual={actual}')
    if facts:
        message = 'Line net amount does not equal quantity times unit price.'
    elif unknown:
        facts = ['R007:UNKNOWN']
        message = '; '.join(sorted(set(unknown)))
    else:
        facts = ['R007:OK']
        message = 'All line amounts equal quantity times unit price.'
    return {'facts': facts, 'evidence_paths': paths, 'line_ids': ids, 'message': message}


def r008_details(c, cfg):
    policy = cfg['policies'].get(c['policy_id'])
    if policy is None:
        return {'facts': ['R008:UNKNOWN'], 'evidence_paths': ['/policy_id'], 'line_ids': [],
                'message': 'Policy is unknown.'}
    required = set(policy['auth_required_services'])
    paths = []
    unknown_lines = []
    failed_lines = []
    relevant = []
    for i, l in enumerate(c['lines']):
        code = l['service_code']
        if empty(code) or code not in cfg['services']:
            unknown_lines.append(i)
            paths.append(f'/lines/{i}/service_code')
            continue
        if code not in required:
            continue
        relevant.append(i)
        paths.extend([f'/lines/{i}/service_code', f'/lines/{i}/authorization_id'])
        if empty(l['authorization_id']):
            failed_lines.append(i)
    ids = [c['lines'][i]['line_id'] for i in sorted(set(failed_lines))]
    if failed_lines:
        facts = [f'R008:MISSING_AUTH:/lines/{i}/authorization_id' for i in sorted(set(failed_lines))]
        message = 'Required authorization reference is missing.'
    elif unknown_lines:
        facts = ['R008:UNKNOWN']
        message = 'Some line service codes are unknown; cannot determine authorization requirement.'
    elif relevant:
        facts = ['R008:OK']
        message = 'All authorization-required lines carry an authorization reference.'
    else:
        facts = ['R008:NOT_APPLICABLE']
        message = 'No line requires an authorization reference under this policy.'
    return {'facts': facts, 'evidence_paths': paths or ['/policy_id'], 'line_ids': ids, 'message': message}


def r009_details(c, cfg):
    policy = cfg['policies'].get(c['policy_id'])
    if policy is None:
        return {'facts': ['R009:UNKNOWN'], 'evidence_paths': ['/policy_id'], 'line_ids': [],
                'message': 'Policy is unknown.'}
    required = set(policy['auth_required_services'])
    auths_by_id = {a['authorization_id']: a for a in c['authorizations']}
    qty_by_auth = {}
    qty_unknown_auth = set()  # a shared authorization whose total cannot be summed
    for l in c['lines']:
        aid = l['authorization_id']
        if not aid:
            continue
        if isinstance(l['quantity'], (int, float)) and not isinstance(l['quantity'], bool):
            qty_by_auth[aid] = qty_by_auth.get(aid, 0) + l['quantity']
        else:
            qty_unknown_auth.add(aid)
    paths = ['/policy_id']
    unknown_lines = []
    failed_lines = []
    relevant = []
    for i, l in enumerate(c['lines']):
        code = l['service_code']
        if empty(code) or code not in cfg['services']:
            unknown_lines.append(i)
            continue
        if code not in required:
            continue
        relevant.append(i)
        aid = l['authorization_id']
        paths.extend([f'/lines/{i}/service_code', f'/lines/{i}/authorization_id'])
        if empty(aid):
            unknown_lines.append(i)
            continue
        auth = auths_by_id.get(aid)
        if auth is None:
            failed_lines.append(i)
            paths.append('/authorizations')
            continue
        sd = valid_date(l['service_date'])
        vf, vt = valid_date(auth['valid_from']), valid_date(auth['valid_to'])
        cap = auth['max_quantity']
        # docs/04: a proven violation gives FAIL even when another comparison input is missing.
        mismatch = False
        unknown = False
        for mine, theirs in ((c['patient_id'], auth['patient_id']), (code, auth['service_code'])):
            if empty(theirs):
                unknown = True
            elif theirs != mine:
                mismatch = True
        if empty(auth['status']):
            unknown = True
        elif auth['status'] != 'approved':
            mismatch = True
        if sd is None or vf is None or vt is None:
            unknown = True
        elif sd < vf or sd > vt:
            mismatch = True
        if cap is None or aid in qty_unknown_auth:
            unknown = True
        elif qty_by_auth.get(aid, 0) > cap:
            mismatch = True
        paths.append(f'/lines/{i}/service_date')
        if mismatch:
            failed_lines.append(i)
        elif unknown:
            unknown_lines.append(i)
    ids = [c['lines'][i]['line_id'] for i in sorted(set(failed_lines))]
    if failed_lines:
        facts = [f'R009:MISMATCH:/lines/{i}/authorization_id' for i in sorted(set(failed_lines))]
        message = 'Authorization record does not match the service.'
    elif unknown_lines:
        facts = ['R009:UNKNOWN']
        message = 'Missing inputs prevent matching the authorization record.'
    elif relevant:
        facts = ['R009:OK']
        message = 'Authorization records match the required services.'
    else:
        facts = ['R009:NOT_APPLICABLE']
        message = 'No line requires an authorization record under this policy.'
    return {'facts': facts, 'evidence_paths': paths, 'line_ids': ids, 'message': message}


def r010_details(c, cfg):
    policy = cfg['policies'].get(c['policy_id'])
    if policy is None:
        return {'facts': ['R010:UNKNOWN'], 'evidence_paths': ['/policy_id'], 'line_ids': [],
                'message': 'Policy is unknown.'}
    required_docs = policy['required_documents']
    paths = ['/attachments']
    unknown_lines = []
    failed_lines = []
    relevant = []
    for i, l in enumerate(c['lines']):
        code = l['service_code']
        if empty(code) or code not in cfg['services']:
            unknown_lines.append(i)
            continue
        if code not in required_docs:
            continue
        relevant.append(i)
        req_type = required_docs[code]
        sd = l['service_date']
        paths.extend([f'/lines/{i}/service_code', f'/lines/{i}/service_date'])
        if empty(sd) or not valid_date(sd):
            unknown_lines.append(i)
            continue
        matches = [
            a for a in c['attachments']
            if a['type'] == req_type and a['patient_id'] == c['patient_id']
            and a['service_code'] == code and a['service_date'] == sd
        ]
        if not matches:
            failed_lines.append(i)
        elif any(a['document_status'] == 'final' for a in matches):
            continue
        else:
            unknown_lines.append(i)
    ids = [c['lines'][i]['line_id'] for i in sorted(set(failed_lines))]
    if failed_lines:
        facts = [f'R010:MISSING_DOC:/lines/{i}/service_code' for i in sorted(set(failed_lines))]
        message = 'Required supporting document is absent or mismatched.'
    elif unknown_lines:
        facts = ['R010:UNKNOWN']
        message = 'Only draft or uncertain matching documentation is available.'
    elif relevant:
        facts = ['R010:OK']
        message = 'Required supporting documents are present and final.'
    else:
        facts = ['R010:NOT_APPLICABLE']
        message = 'No line requires a supporting document under this policy.'
    return {'facts': facts, 'evidence_paths': paths, 'line_ids': ids, 'message': message}


def r011_details(c, cfg):
    services = cfg['services']
    paths = []
    unknown_lines = []
    failed_lines = []
    for i, l in enumerate(c['lines']):
        code = l['service_code']
        paths.append(f'/lines/{i}/service_code')
        if empty(code):
            unknown_lines.append(i)
        elif code not in services:
            failed_lines.append(i)
    ids = [c['lines'][i]['line_id'] for i in sorted(set(failed_lines))]
    if failed_lines:
        facts = [f'R011:NOT_CATALOGUED:/lines/{i}/service_code' for i in sorted(set(failed_lines))]
        message = 'Service code is not in the fictional catalogue.'
    elif unknown_lines:
        facts = ['R011:UNKNOWN']
        message = 'Service code is missing.'
    else:
        facts = ['R011:OK']
        message = 'All service codes are in the fictional catalogue.'
    return {'facts': facts, 'evidence_paths': paths, 'line_ids': ids, 'message': message}


def r012_details(c):
    amounts = [l['net_amount'] for l in c['lines']]
    paths = ['/total_amount'] + [f'/lines/{i}/net_amount' for i in range(len(c['lines']))]
    if c['total_amount'] is None or any(a is None for a in amounts):
        facts = ['R012:UNKNOWN']
        message = 'Missing amount inputs prevent totalling.'
    else:
        with localcontext(_WIDE):
            expected = sum((Decimal(str(a)) for a in amounts), Decimal('0')).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP)
            actual = Decimal(str(c['total_amount']))
            off = abs(expected - actual) > Decimal('0.01')
        if off:
            facts = [f'R012:MISMATCH:total_amount={actual}:expected={expected}']
            message = 'Claim total does not equal the sum of line amounts.'
        else:
            facts = ['R012:OK']
            message = 'Claim total equals the sum of line amounts.'
    return {'facts': facts, 'evidence_paths': paths, 'line_ids': [], 'message': message}


def _whole_number(q):
    """True for 3 and for 3.0 (JSON does not distinguish them); False for 1.5, nan, inf and bool."""
    if isinstance(q, bool):
        return False
    return isinstance(q, int) or (isinstance(q, float) and q.is_integer())


def r013_details(c, cfg):
    policy = cfg['policies'].get(c['policy_id'])
    paths = []
    unknown_lines = []
    failed_lines = []
    for i, l in enumerate(c['lines']):
        q, u, code = l['quantity'], l['unit_price'], l['service_code']
        paths.extend([f'/lines/{i}/quantity', f'/lines/{i}/unit_price', f'/lines/{i}/service_code'])
        line_failed = False
        line_unknown = q is None or u is None
        # docs/04: a proven violation gives FAIL even when another input is missing
        if q is not None and not (_whole_number(q) and q > 0):
            line_failed = True
        if u is not None and u <= 0:
            line_failed = True
        if empty(code) or policy is None:
            line_unknown = True
        else:
            max_price = policy['max_unit_price'].get(code)
            max_qty = policy['max_quantity_per_line'].get(code)
            if max_price is None or max_qty is None:
                line_unknown = True
            else:
                if u is not None and u > max_price:
                    line_failed = True
                if q is not None and q > max_qty:
                    line_failed = True
        if line_failed:
            failed_lines.append(i)
        elif line_unknown:
            unknown_lines.append(i)
    ids = [c['lines'][i]['line_id'] for i in sorted(set(failed_lines))]
    if failed_lines:
        facts = [f'R013:LIMIT:/lines/{i}/quantity' for i in sorted(set(failed_lines))]
        message = 'Quantity or unit price violates the fictional limits.'
    elif unknown_lines:
        facts = ['R013:UNKNOWN']
        message = 'Missing inputs, unknown code, or unavailable policy prevent checking limits.'
    else:
        facts = ['R013:OK']
        message = 'All quantities and unit prices are within the fictional limits.'
    return {'facts': facts, 'evidence_paths': paths, 'line_ids': ids, 'message': message}


def r014_details(c, cfg):
    policy = cfg['policies'].get(c['policy_id'])
    sub = valid_date(c['submission_date'])
    service_dates = [valid_date(l['service_date']) for l in c['lines']]
    paths = ['/submission_date', '/policy_id'] + [f'/lines/{i}/service_date' for i in range(len(c['lines']))]
    if policy is None or sub is None or not service_dates or any(d is None for d in service_dates):
        facts = ['R014:UNKNOWN']
        message = 'Missing dates or unavailable policy prevent checking the submission window.'
    else:
        latest = max(service_dates)
        lag = (sub - latest).days
        if lag < 0:
            facts = ['R014:NOT_APPLICABLE']
            message = 'Service date after submission date is handled by R002.'
        elif lag > policy['submission_window_days']:
            facts = [f'R014:LATE:lag={lag}:window={policy["submission_window_days"]}']
            message = 'Submission window exceeded.'
        else:
            facts = ['R014:OK']
            message = 'Submission is within the allowed window.'
    return {'facts': facts, 'evidence_paths': paths, 'line_ids': [], 'message': message}


def r015_details(c, cfg):
    policy = cfg['policies'].get(c['policy_id'])
    cur = c['currency']
    paths = ['/currency', '/policy_id']
    if empty(cur) or policy is None:
        facts = ['R015:UNKNOWN']
        message = 'Currency or policy is unknown.'
    elif cur != policy['currency']:
        facts = [f'R015:MISMATCH:currency={cur}']
        message = 'Currency does not match the policy currency.'
    else:
        facts = ['R015:OK']
        message = 'Currency matches the policy currency.'
    return {'facts': facts, 'evidence_paths': paths, 'line_ids': [], 'message': message}


# --- input sanitizing for rule computation ---------------------------------------------------
# Rules treat None as "unknown" (-> UNABLE_TO_ASSESS). A value of the WRONG TYPE (a string where
# a number belongs, a number where a string belongs, a bool, NaN) is unusable in exactly the same
# way, so rule_view() turns it into None for rule computation only. Evidence is still read from
# the ORIGINAL claim, so what a reviewer sees is what was submitted. Schema-valid claims pass
# through unchanged; only malformed ones are affected, and they degrade to "unknown", never to
# a crash and never to a silent PASS.
import math

_TOP_NUM = ('total_amount',)
_TOP_STR = ('invoice_number', 'member_id', 'diagnosis_code', 'patient_id', 'provider_id', 'payer_id',
            'policy_id', 'submission_date', 'currency')
_COVERAGE_STR = ('coverage_id', 'status', 'beneficiary_patient_id', 'member_id', 'start_date', 'end_date')
_LINE_NUM = ('quantity', 'unit_price', 'net_amount')
_LINE_STR = ('service_code', 'service_date', 'modifier', 'authorization_id')
_AUTH_NUM = ('max_quantity',)
_AUTH_STR = ('authorization_id', 'patient_id', 'service_code', 'status', 'valid_from', 'valid_to')
_ATT_STR = ('attachment_id', 'type', 'patient_id', 'service_code', 'service_date', 'document_status', 'text')


def _clean_num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def _clean_str(v):
    return v if isinstance(v, str) else None


def _clean_row(row, nums, strs):
    """Wrong-typed values, missing keys and non-object rows all become None (unknown)."""
    if not isinstance(row, dict):
        return {k: None for k in nums + strs}
    out = dict(row)
    for k in nums:
        out[k] = _clean_num(out.get(k))
    for k in strs:
        out[k] = _clean_str(out.get(k))
    return out


def rule_view(c):
    """A copy of the claim with wrong-typed values replaced by None (see above)."""
    v = _clean_row(c, _TOP_NUM, _TOP_STR)
    v['coverage'] = _clean_row(c.get('coverage'), (), _COVERAGE_STR)
    for key, nums, strs in (('lines', _LINE_NUM, _LINE_STR), ('authorizations', _AUTH_NUM, _AUTH_STR),
                            ('attachments', (), _ATT_STR)):
        if isinstance(c.get(key), list):
            v[key] = [_clean_row(r, nums, strs) for r in c[key]]
    return v
