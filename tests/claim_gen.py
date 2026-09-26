"""Random claims built from scratch (not mutated from the public data), for differential testing.

Every field is drawn from a pool that includes the values the rulebook draws lines around: policy limits and
one step past them, half-cent prices, 0.01 / 0.02 amount differences, inclusive date edges, wrong-case enums,
null and empty ids, shared authorization ids and quantities right at and just past their maximum.
"""
from datetime import date, timedelta

CODES = ['SVC-CONSULT', 'SVC-LAB', 'SVC-IMAGE', 'SVC-THERAPY', 'SVC-DENTAL', 'SVC-PHARM', 'SVC-NOPE', None]
QUANTITIES = [1, 1, 1, 2, 3, 4, 5, 0, -1, 1.5, 2.0, None]
PRICES = [100, 130, 180, 260, 260.01, 350, 450, 2200, 2201, 0, -5, None, 0.335, 2.675]


def _day(rng, base, spread, p_none=0.05):
    if rng.random() < p_none:
        return None
    return (base + timedelta(days=rng.randint(-spread, spread))).isoformat()


def _random_claim(rng):
    base = date(2026, rng.randint(1, 12), rng.randint(1, 28))
    pid = f'PAT-{rng.randint(1, 3)}'
    mem = f'MEM-{rng.randint(1, 3)}'
    claim = {
        'schema_version': '1.0.0', 'claim_id': f'CG-{rng.randint(0, 10 ** 9)}',
        'invoice_number': rng.choice(['INV-1', '']), 'patient_id': pid, 'member_id': rng.choice([mem, None, mem.lower()]),
        'provider_id': rng.choice(['EDU-PROV-01', 'EDU-PROV-02', 'EDU-PROV-03', 'EDU-PROV-04']), 'payer_id': 'EDU-PAYER',
        'policy_id': rng.choice(['EDU-BASIC', 'EDU-PLUS', 'EDU-PLUS', 'EDU-X']),
        'diagnosis_code': rng.choice(['DX-EDU-01', None]),
        'submission_date': (base + timedelta(days=rng.randint(0, 90))).isoformat(),
        'currency': rng.choice(['SAR', 'SAR', 'SAR', 'USD', 'sar']), 'total_amount': None,
        'coverage': {'coverage_id': 'C', 'status': rng.choice(['active', 'active', 'active', 'terminated', 'Active', None]),
                     'beneficiary_patient_id': rng.choice([pid, pid, 'PAT-9', None]),
                     'member_id': rng.choice([mem, mem, 'MEM-9', None]),
                     'start_date': _day(rng, base, 120), 'end_date': _day(rng, base + timedelta(days=60), 120)},
        'lines': [], 'authorizations': [], 'attachments': [], 'notes': 'Synthetic claim.'}
    auth_ids = [f'AUTH-{i}' for i in range(3)]
    for i in range(rng.randint(1, 6)):
        q, u = rng.choice(QUANTITIES), rng.choice(PRICES)
        net = None if q is None or u is None else round(q * u + rng.choice([0, 0, 0, 0.01, -0.01, 0.02, 5]), 2)
        claim['lines'].append({
            'line_id': f'L{i}', 'service_code': rng.choice(CODES), 'service_date': _day(rng, base, 40, 0.03),
            'modifier': rng.choice([None, '', '25']), 'quantity': q, 'unit_price': u, 'net_amount': net,
            'authorization_id': rng.choice([None, ''] + auth_ids + ['AUTH-Z'])})
    if rng.random() < 0.2:  # a repeated service line, possibly with the null / empty modifier spelled differently
        twin = dict(rng.choice(claim['lines']), line_id=f'L{len(claim["lines"])}')
        twin['modifier'] = rng.choice([twin['modifier'], None, ''])
        claim['lines'].append(twin)
    nets = [l['net_amount'] for l in claim['lines']]
    if None not in nets and rng.random() >= 0.05:
        claim['total_amount'] = round(sum(nets) + rng.choice([0, 0, 0, 0.01, 0.02, -0.01]), 2)
    for aid in auth_ids:
        if rng.random() < 0.7:
            claim['authorizations'].append({
                'authorization_id': aid, 'patient_id': rng.choice([pid, pid, 'PAT-9', None]),
                'service_code': rng.choice(CODES[:6] + [None]), 'status': rng.choice(['approved', 'approved', 'pending', None, 'APPROVED']),
                'valid_from': _day(rng, base, 40), 'valid_to': _day(rng, base + timedelta(days=20), 40),
                'max_quantity': rng.choice([1, 2, 3, 5, None, 0])})
    for l in claim['lines']:
        if rng.random() < 0.5 and l['service_code'] and l['service_date']:
            claim['attachments'].append({
                'attachment_id': f'D{rng.randint(0, 9999)}', 'type': rng.choice(['imaging-report', 'service-note', 'other']),
                'patient_id': rng.choice([pid, pid, 'PAT-9']),
                'service_code': l['service_code'] if rng.random() < 0.8 else 'SVC-LAB',
                'service_date': l['service_date'] if rng.random() < 0.8 else _day(rng, base, 10),
                'document_status': rng.choice(['final', 'draft', 'final', 'unknown', None]), 'text': 'SYNTHETIC'})
    return claim


# What a clean line of each service looks like under the policy limits (docs/04): price, quantity, and whether it needs
# an authorization or a document.
_CLEAN = {'SVC-CONSULT': (180, 1, None), 'SVC-LAB': (120, 3, None), 'SVC-IMAGE': (1500, 1, 'imaging-report'),
          'SVC-THERAPY': (240, 4, None), 'SVC-DENTAL': (400, 2, 'service-note'), 'SVC-PHARM': (20, 10, None)}
_AUTH_REQUIRED = ('SVC-IMAGE', 'SVC-THERAPY')


def coherent_claim(rng):
    """A claim that satisfies every rule, so that random damage to it lands on individual rules instead of on all of them."""
    base = date(2026, rng.randint(2, 11), rng.randint(1, 28))
    pid, mem = 'PAT-1', 'MEM-1'
    claim = {
        'schema_version': '1.0.0', 'claim_id': f'CG-{rng.randint(0, 10 ** 9)}', 'invoice_number': 'INV-1', 'patient_id': pid,
        'member_id': mem, 'provider_id': 'EDU-PROV-01', 'payer_id': 'EDU-PAYER', 'policy_id': rng.choice(['EDU-BASIC', 'EDU-PLUS']),
        'diagnosis_code': 'DX-EDU-01', 'submission_date': (base + timedelta(days=rng.randint(0, 25))).isoformat(),
        'currency': 'SAR', 'total_amount': 0,
        'coverage': {'coverage_id': 'C', 'status': 'active', 'beneficiary_patient_id': pid, 'member_id': mem,
                     'start_date': (base - timedelta(days=60)).isoformat(), 'end_date': (base + timedelta(days=90)).isoformat()},
        'lines': [], 'authorizations': [], 'attachments': [], 'notes': 'Synthetic claim.'}
    for i, code in enumerate(rng.sample(list(_CLEAN), rng.randint(1, 4))):
        price, max_q, doc = _CLEAN[code]
        qty = rng.randint(1, max_q)
        day_ = (base + timedelta(days=rng.randint(-5, 0))).isoformat()
        line = {'line_id': f'L{i}', 'service_code': code, 'service_date': day_, 'modifier': None, 'quantity': qty,
                'unit_price': price, 'net_amount': float(qty * price), 'authorization_id': None}
        if code in _AUTH_REQUIRED:
            line['authorization_id'] = f'AUTH-{i}'
            claim['authorizations'].append({
                'authorization_id': f'AUTH-{i}', 'patient_id': pid, 'service_code': code, 'status': 'approved',
                'valid_from': (base - timedelta(days=30)).isoformat(), 'valid_to': (base + timedelta(days=30)).isoformat(),
                'max_quantity': max_q})
        if doc:
            claim['attachments'].append({
                'attachment_id': f'DOC-{i}', 'type': doc, 'patient_id': pid, 'service_code': code, 'service_date': day_,
                'document_status': 'final', 'text': 'SYNTHETIC'})
        claim['lines'].append(line)
    claim['total_amount'] = float(sum(l['net_amount'] for l in claim['lines']))
    return claim


_DAMAGE = {
    'status': ['terminated', None, 'Active'], 'currency': ['USD', 'sar', None], 'provider_id': ['EDU-PROV-09'],
    'policy_id': ['EDU-GHOST'], 'total_amount': [None, 1.0, 0], 'member_id': ['MEM-2', None, 'mem-1'],
    'quantity': [None, 0, 1.5, 99, -1], 'unit_price': [None, 0, 5000], 'net_amount': [None, 1, -1],
    'service_date': [None, '2027-01-01', '2025-01-01'], 'service_code': [None, 'SVC-NOPE'], 'authorization_id': [None, '', 'AUTH-Z'],
    'valid_to': [None, '2020-01-01'], 'valid_from': [None, '2099-01-01'], 'max_quantity': [None, 0], 'document_status': ['draft', None],
    'type': ['service-note', None]}


def damaged_coherent_claim(rng):
    claim = coherent_claim(rng)
    for _ in range(rng.choice((0, 1, 1, 2))):
        key = rng.choice(list(_DAMAGE))
        value = rng.choice(_DAMAGE[key])
        if key in ('status',):
            claim['coverage'][key] = value
        elif key in ('currency', 'provider_id', 'policy_id', 'total_amount', 'member_id'):
            claim[key] = value
        else:
            for pool in ('lines', 'authorizations', 'attachments'):
                rows = [r for r in claim[pool] if key in r]
                if rows:
                    rng.choice(rows)[key] = value
                    break
    return claim


def random_claim(rng):
    """Half coherent-then-damaged, half fully random: reaches PASS as well as every kind of FAIL and UNABLE."""
    return damaged_coherent_claim(rng) if rng.random() < 0.5 else _random_claim(rng)
