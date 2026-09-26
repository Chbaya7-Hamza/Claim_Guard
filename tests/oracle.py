"""Independent reference checker for the 15 fictional rules.

Written only from the wording of rules/rules.json and docs/04_Rulebook.md. It imports nothing from the
engine (src/facts_extractor.py, src/yara_engine.py, src/engine_core.py) so it cannot share a bug with it.
It exists to be compared against the engine on generated claims; where the two disagree the rulebook
wording, not this file, decides which side is wrong.

Verdict precedence inside every rule (docs/04, "Shared evaluation conventions"):
a proven violation -> FAIL; otherwise missing necessary evidence -> UNABLE_TO_ASSESS;
otherwise PASS, or NOT_APPLICABLE when the rule does not apply.

Conventions taken from the supplied baseline (src/engine_core.py) and the handbook rather than invented:
"empty" means null or a whitespace-only string; identifiers and enum values compare exactly (case sensitive).
"""
import json
import re
from datetime import date
from decimal import Context, Decimal, ROUND_HALF_UP
from pathlib import Path

PASS, FAIL, UNABLE, NA = 'PASS', 'FAIL', 'UNABLE_TO_ASSESS', 'NOT_APPLICABLE'
CENT = Decimal('0.01')
_ISO = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def load_rules_pack(root):
    root = Path(root)
    return {n: json.loads((root / 'rules' / f'{n}.json').read_text(encoding='utf-8')) for n in ('policies', 'services')}


def day(v):
    """A calendar day, or None when the value is not a well-formed ISO date (no trimming, no repair)."""
    if not isinstance(v, str) or not _ISO.match(v):
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def num(v):
    """Exact Decimal of a JSON number, built from its text (never from the binary float); None if not a number."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    if isinstance(v, float) and v != v or v in (float('inf'), float('-inf')):
        return None  # NaN / Infinity are not amounts: unknown, exactly like a missing value
    return Decimal(str(v))


def empty(v):
    return v is None or (isinstance(v, str) and not v.strip())


_WIDE = Context(prec=5000, rounding=ROUND_HALF_UP, Emax=999999, Emin=-999999)


def money(d):
    return d.quantize(CENT, context=_WIDE)


def verdict(fail, unable, ok=PASS):
    return FAIL if fail else UNABLE if unable else ok


def _policy(c, pack):
    return pack['policies'].get(c['policy_id'])


def _catalogue(pack):
    return pack['services']


def _unusable_number(v):
    return isinstance(v, float) and (v != v or v in (float('inf'), float('-inf')))


def r001(c, pack):
    # NaN / Infinity are not in the rulebook. Treating them as absent information is the conservative reading
    # (the claim is flagged for a human) and is the engine's documented choice too.
    bad = any(empty(c[k]) for k in ('invoice_number', 'member_id', 'diagnosis_code'))
    for l in c['lines']:
        bad = bad or any(empty(l[k]) for k in ('service_date', 'service_code', 'quantity', 'unit_price', 'net_amount'))
        bad = bad or any(_unusable_number(l[k]) for k in ('quantity', 'unit_price', 'net_amount'))
    return FAIL if bad else PASS


def r002(c, pack):
    sub = day(c['submission_date'])
    fail = unable = False
    for l in c['lines']:
        d = day(l['service_date'])
        if d is None or sub is None:
            unable = True
        elif d > sub:
            fail = True
    return verdict(fail, unable)


def r003(c, pack):
    cv = c['coverage']
    start, end = day(cv.get('start_date')), day(cv.get('end_date'))
    fail = unable = False
    if empty(cv.get('status')):
        unable = True
    elif cv['status'] != 'active':
        fail = True
    if start is None or end is None:
        unable = True
    for l in c['lines']:
        d = day(l['service_date'])
        if d is None:
            unable = True
        elif (start is not None and d < start) or (end is not None and d > end):
            fail = True
    return verdict(fail, unable)


def r004(c, pack):
    cv = c['coverage']
    fail = unable = False
    for mine, theirs in ((c['patient_id'], cv.get('beneficiary_patient_id')), (c['member_id'], cv.get('member_id'))):
        if empty(mine) or empty(theirs):
            unable = True
        elif mine != theirs:
            fail = True
    return verdict(fail, unable)


def r005(c, pack):
    pol = _policy(c, pack)
    if empty(c['provider_id']) or pol is None:
        return UNABLE
    return PASS if c['provider_id'] in pol['allowed_providers'] else FAIL


def r006(c, pack):
    seen, dup, missing = set(), False, False
    for l in c['lines']:
        if empty(l['service_code']) or day(l['service_date']) is None:
            missing = True
            continue
        key = (l['service_code'], l['service_date'], l['modifier'] or '')
        dup = dup or key in seen
        seen.add(key)
    return verdict(dup, missing)


def r007(c, pack):
    fail = unable = False
    for l in c['lines']:
        q, u, n = num(l['quantity']), num(l['unit_price']), num(l['net_amount'])
        if None in (q, u, n):
            unable = True
        elif abs(n - money(q * u)) > CENT:
            fail = True
    return verdict(fail, unable)


def _known_code(code, pack):
    return not empty(code) and code in _catalogue(pack)


def r008(c, pack):
    pol = _policy(c, pack)
    if pol is None:
        return UNABLE
    fail = unable = required = False
    for l in c['lines']:
        if not _known_code(l['service_code'], pack):
            unable = True
        elif l['service_code'] in pol['auth_required_services']:
            required = True
            fail = fail or empty(l['authorization_id'])
    return verdict(fail, unable, PASS if required else NA)


def r009(c, pack):
    pol = _policy(c, pack)
    if pol is None:
        return UNABLE
    fail = unable = required = False
    auths = c['authorizations']
    for l in c['lines']:
        if not _known_code(l['service_code'], pack):
            unable = True
            continue
        if l['service_code'] not in pol['auth_required_services']:
            continue
        required = True
        if empty(l['authorization_id']):
            unable = True  # R008 owns the missing reference
            continue
        rec = next((a for a in auths if a['authorization_id'] == l['authorization_id']), None)
        if rec is None:
            fail = True
            continue
        if empty(rec.get('patient_id')):
            unable = True
        elif rec['patient_id'] != c['patient_id']:
            fail = True
        if empty(rec.get('service_code')):
            unable = True
        elif rec['service_code'] != l['service_code']:
            fail = True
        if empty(rec.get('status')):
            unable = True
        elif rec['status'] != 'approved':
            fail = True
        d, lo, hi = day(l['service_date']), day(rec.get('valid_from')), day(rec.get('valid_to'))
        if d is None or lo is None or hi is None:
            unable = True
        elif not lo <= d <= hi:
            fail = True
    for aid in {l['authorization_id'] for l in c['lines']
                if not empty(l['authorization_id']) and _known_code(l['service_code'], pack)
                and l['service_code'] in pol['auth_required_services']}:
        rec = next((a for a in auths if a['authorization_id'] == aid), None)
        if rec is None:
            continue
        cap = num(rec.get('max_quantity'))
        qs = [num(l['quantity']) for l in c['lines'] if l['authorization_id'] == aid]
        if cap is None or None in qs:
            unable = True
        elif sum(qs) > cap:
            fail = True
    return verdict(fail, unable, PASS if required else NA)


def r010(c, pack):
    pol = _policy(c, pack)
    if pol is None:
        return UNABLE
    fail = unable = required = False
    for l in c['lines']:
        if not _known_code(l['service_code'], pack):
            unable = True
            continue
        need = pol['required_documents'].get(l['service_code'])
        if need is None:
            continue
        required = True
        d = day(l['service_date'])
        if d is None:
            unable = True
            continue
        hits = [a for a in c['attachments'] if a.get('type') == need and a.get('patient_id') == c['patient_id']
                and a.get('service_code') == l['service_code'] and day(a.get('service_date')) == d]
        if not hits:
            fail = True
        elif not any(a.get('document_status') == 'final' for a in hits):
            unable = True
    return verdict(fail, unable, PASS if required else NA)


def r011(c, pack):
    fail = unable = False
    for l in c['lines']:
        if empty(l['service_code']):
            unable = True
        elif l['service_code'] not in _catalogue(pack):
            fail = True
    return verdict(fail, unable)


def r012(c, pack):
    total = num(c['total_amount'])
    nets = [num(l['net_amount']) for l in c['lines']]
    if total is None or None in nets:
        return UNABLE
    return FAIL if abs(total - money(sum(nets))) > CENT else PASS


def r013(c, pack):
    pol = _policy(c, pack)
    fail = unable = False
    for l in c['lines']:
        q, u = num(l['quantity']), num(l['unit_price'])
        limits = pol is not None and not empty(l['service_code'])             and l['service_code'] in pol['max_unit_price'] and l['service_code'] in pol['max_quantity_per_line']
        if q is None or u is None or not limits:
            unable = True
        # each known value is checked on its own: a violation is proven even when another input is missing
        if q is not None:
            fail = fail or q <= 0 or q != q.to_integral_value()
            fail = fail or (limits and q > num(pol['max_quantity_per_line'][l['service_code']]))
        if u is not None:
            fail = fail or u <= 0
            fail = fail or (limits and u > num(pol['max_unit_price'][l['service_code']]))
    return verdict(fail, unable)


def r014(c, pack):
    pol = _policy(c, pack)
    sub = day(c['submission_date'])
    dates = [day(l['service_date']) for l in c['lines']]
    if pol is None or sub is None or not dates or None in dates:
        return UNABLE
    lag = (sub - max(dates)).days
    if lag < 0:
        return NA
    return FAIL if lag > pol['submission_window_days'] else PASS


def r015(c, pack):
    pol = _policy(c, pack)
    if empty(c['currency']) or pol is None:
        return UNABLE
    return PASS if c['currency'] == pol['currency'] else FAIL


RULES = {f'R{i:03d}': fn for i, fn in enumerate(
    (r001, r002, r003, r004, r005, r006, r007, r008, r009, r010, r011, r012, r013, r014, r015), start=1)}


def evaluate(claim, pack):
    """{rule_id: status} for one claim."""
    return {rid: fn(claim, pack) for rid, fn in RULES.items()}
