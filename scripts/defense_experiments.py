"""Experiments that back technical decisions (docs/27). Each one has a baseline or a control that
could make the decision look wrong, and every result is written to outputs/defense/ as recorded.

    python scripts/defense_experiments.py failclosed   # a crash in each of the 15 rules
    python scripts/defense_experiments.py injection    # forged facts, with and without percent-encoding
    python scripts/defense_experiments.py tamper       # audit-log tampering vs chain / +anchor / +keyed anchor
    python scripts/defense_experiments.py all
"""
import copy
import json
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
OUT = ROOT / 'outputs' / 'defense'

import audit_log  # noqa: E402
import facts_extractor  # noqa: E402
import yara_engine  # noqa: E402
from audit import digest, verify  # noqa: E402
from engine_core import config  # noqa: E402
from jsonl_reader import parse_json, read_lines  # noqa: E402


def load_claims(n):
    claims = []
    for _, line, err in read_lines(ROOT / 'data' / 'development' / 'claims.jsonl'):
        if err:
            continue
        c, perr = parse_json(line)
        if not perr:
            claims.append(c)
        if len(claims) >= n:
            break
    return claims


def statuses(claim, cfg):
    return {r['rule_id']: r['status'] for r in yara_engine.evaluate(claim, cfg)}


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f'{name}.json').write_text(json.dumps(data, indent=2), encoding='utf-8')


# ---------------------------------------------------------------- fail-closed
def failclosed(n_claims=100):
    cfg = config(ROOT)
    claims = load_claims(n_claims)
    baseline = [statuses(c, cfg) for c in claims]
    original = dict(yara_engine.DETAIL_FUNCS)
    per_rule = {}
    for rid in original:
        bad_pass = collateral = not_unable = 0
        import logging
        logging.getLogger('yara_engine').setLevel(logging.CRITICAL)
        yara_engine.DETAIL_FUNCS[rid] = lambda c, cfg_: 1 / 0
        try:
            for c, base in zip(claims, baseline):
                got = statuses(c, cfg)
                if got[rid] != 'UNABLE_TO_ASSESS':
                    not_unable += 1
                if got[rid] == 'PASS':
                    bad_pass += 1
                collateral += sum(1 for k in base if k != rid and got[k] != base[k])
        finally:
            yara_engine.DETAIL_FUNCS[rid] = original[rid]
        per_rule[rid] = {'claims': len(claims), 'crashed_rule_not_unable': not_unable,
                         'crashed_rule_became_pass': bad_pass, 'other_rules_changed': collateral}
    res = {'experiment': 'failclosed', 'claims': len(claims), 'per_rule': per_rule,
           'all_fail_closed': all(v['crashed_rule_not_unable'] == 0 and v['other_rules_changed'] == 0 and
                                  v['crashed_rule_became_pass'] == 0 for v in per_rule.values())}
    save('failclosed', res)
    return res


# ---------------------------------------------------------------- fact injection
def _string_fields(claim):
    top = ['invoice_number', 'patient_id', 'member_id', 'provider_id', 'payer_id', 'policy_id',
           'diagnosis_code', 'currency', 'notes']
    fields = [(('top', k)) for k in top if isinstance(claim.get(k), str)]
    if claim.get('lines'):
        for k in ('line_id', 'service_code', 'authorization_id', 'modifier'):
            if isinstance(claim['lines'][0].get(k), str):
                fields.append(('line0', k))
    return fields


def _set(claim, field, value):
    c = copy.deepcopy(claim)
    where, k = field
    (c if where == 'top' else c['lines'][0])[k] = value
    return c


def _collect_fact_lines(claims, cfg):
    """Real fact lines the engine emits for every rule/outcome, used as forgery payloads."""
    seen = {}
    for c in claims:
        view = facts_extractor.rule_view(c)
        for rid, fn in yara_engine.DETAIL_FUNCS.items():
            try:
                for f in fn(view, cfg)['facts']:
                    seen.setdefault((rid, f.split(':')[1] if ':' in f else ''), f)
            except Exception:
                pass
    return list(seen.values())


def _run_injection(claims, cfg, payloads):
    forged = trials = 0
    examples = []
    for c in claims:
        base = statuses(c, cfg)
        for field in _string_fields(c):
            benign = statuses(_set(c, field, 'ZZZ-BENIGN'), cfg)
            legit = {k for k in base if benign[k] != base[k]}
            for p in payloads:
                for shape in (p, 'x\n' + p, p + '\n'):
                    trials += 1
                    try:
                        got = statuses(_set(c, field, shape), cfg)
                    except Exception:
                        continue
                    flips = {k for k in base if got[k] != base[k]} - legit
                    if flips:
                        forged += 1
                        if len(examples) < 5:
                            examples.append({'claim_id': c['claim_id'], 'field': field, 'payload': shape[:80],
                                             'rules_flipped': sorted(flips)})
    return {'trials': trials, 'forged_outcomes': forged, 'examples': examples}


def injection(n_claims=20):
    cfg = config(ROOT)
    claims = load_claims(n_claims)
    payloads = _collect_fact_lines(load_claims(100), cfg)
    encoded = _run_injection(claims, cfg, payloads)
    real_q = facts_extractor._q
    facts_extractor._q = lambda v: str(v)  # baseline: no percent-encoding
    try:
        unencoded = _run_injection(claims, cfg, payloads)
    finally:
        facts_extractor._q = real_q
    res = {'experiment': 'injection', 'claims': len(claims), 'payloads': len(payloads),
           'with_encoding': encoded, 'without_encoding_baseline': unencoded}
    save('injection', res)
    return res


# ---------------------------------------------------------------- audit tamper matrix
def _make_log(d, n=40, key=None):
    if key:
        os.environ[audit_log.ANCHOR_KEY_ENV] = key
    else:
        os.environ.pop(audit_log.ANCHOR_KEY_ENV, None)
    p = Path(d) / 'audit.jsonl'
    log = audit_log.AuditLog(p)
    log._write([{'event_type': 'rule_check', 'claim_id': f'CG-{i}', 'rule_id': 'R001', 'status': 'PASS'}
                for i in range(n)])
    return p


def _rows(p):
    return [json.loads(l) for l in p.read_text(encoding='utf-8').split('\n') if l.strip()]


def _write_rows(p, rows):
    p.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')


def _rechain(rows, start=0):
    for i in range(start, len(rows)):
        rows[i]['sequence'] = i + 1
        rows[i]['previous_hash'] = rows[i - 1]['hash'] if i else '0' * 64
        body = {k: rows[i][k] for k in ('sequence', 'recorded_at', 'previous_hash', 'event')}
        rows[i]['hash'] = digest(body)
    return rows


def _write_anchor(p, rows, mac_key=None):
    a = {'head': rows[-1]['hash'], 'count': len(rows), 'written_at': 'x', 'note': 'forged'}
    if mac_key:
        import hashlib
        import hmac
        a['mac'] = hmac.new(mac_key.encode(), f"{a['head']}|{a['count']}".encode('ascii'), hashlib.sha256).hexdigest()
    p.with_name(p.name + '.head.json').write_text(json.dumps(a), encoding='utf-8')


ATTACKS = {}


def attack(fn):
    ATTACKS[fn.__name__] = fn
    return fn


@attack
def edit_row_no_rechain(p, key):
    r = _rows(p); r[10]['event']['status'] = 'FAIL'; _write_rows(p, r)


@attack
def delete_middle_row(p, key):
    r = _rows(p); del r[15]; _write_rows(p, r)


@attack
def swap_two_rows(p, key):
    r = _rows(p); r[5], r[6] = r[6], r[5]; _write_rows(p, r)


@attack
def truncate_tail(p, key):
    r = _rows(p); _write_rows(p, r[:-5])


@attack
def edit_and_rechain_anchor_untouched(p, key):
    r = _rows(p); r[10]['event']['status'] = 'FAIL'; _write_rows(p, _rechain(r, 10))


@attack
def rewrite_all_and_anchor_without_key(p, key):
    r = _rows(p); r[10]['event']['status'] = 'FAIL'; r = _rechain(r, 10); _write_rows(p, r); _write_anchor(p, r)


@attack
def append_forged_rows_valid_chain(p, key):
    r = _rows(p)
    for i in range(3):
        r.append({'sequence': len(r) + 1, 'recorded_at': 'x', 'previous_hash': '', 'event': {
            'event_type': 'rule_check', 'claim_id': f'FORGED-{i}', 'rule_id': 'R001', 'status': 'PASS'}, 'hash': ''})
    _write_rows(p, _rechain(r, len(r) - 3))


@attack
def append_forged_rows_and_reanchor_without_key(p, key):
    append_forged_rows_valid_chain(p, key)
    _write_anchor(p, _rows(p))


def _detect(verifier, p):
    try:
        if verifier == 'chain_only':
            verify(p)
        else:
            audit_log.verify_with_anchor(p, strict=(verifier == 'chain_plus_anchor_strict'))
        return False
    except Exception:
        return True


def tamper():
    results = {}
    for cfgname, key in (('no_key', None), ('hmac_key', 'experiment-key')):
        results[cfgname] = {}
        for name, fn in ATTACKS.items():
            row = {}
            for verifier in ('chain_only', 'chain_plus_anchor', 'chain_plus_anchor_strict'):
                d = tempfile.mkdtemp()
                try:
                    p = _make_log(d, key=key)
                    # an attacker who can write the files does not hold the key
                    os.environ.pop(audit_log.ANCHOR_KEY_ENV, None)
                    if name == 'rewrite_all_and_anchor_without_key':
                        pass
                    fn(p, key)
                    if key:
                        os.environ[audit_log.ANCHOR_KEY_ENV] = key  # verifier holds the key
                    row[verifier] = _detect(verifier, p)
                finally:
                    shutil.rmtree(d, ignore_errors=True)
            results[cfgname][name] = row
    os.environ.pop(audit_log.ANCHOR_KEY_ENV, None)
    res = {'experiment': 'tamper', 'attacks': list(ATTACKS), 'detected': results,
           'note': 'True = tampering detected. plain unchained log: nothing to verify, detection 0 by definition.'}
    save('tamper', res)
    return res


# ---------------------------------------------------------------- validation-layer ablation
def _load_all_cases():
    cases = {}
    for f in sorted((ROOT / 'exercises').glob('*variants.jsonl')) + [ROOT / 'exercises' / 'llm_explanation_cases.jsonl']:
        for line in f.read_text(encoding='utf-8').splitlines():
            if line.strip():
                c = json.loads(line)
                cases[c['case_id']] = c
    return cases


def _parse_reply(text):
    t = text.strip()
    if t.startswith('```'):
        t = t.strip('`')
        t = t[4:] if t.lower().startswith('json') else t
    return json.loads(t)


def ablation():
    import re as _re
    import llm_adapter as la
    cases = _load_all_cases()
    layers = ['schema', 'currency', 'relative_time', 'clinical_fraud', 'validity', 'garbled']
    n = unparse = 0
    rejected_by = {k: 0 for k in layers}
    only_by = {k: 0 for k in layers}
    repair_rescued = 0
    any_reject = 0
    mismatch = 0
    examples = {k: [] for k in layers}

    def grounding_failures(out, finding, rule):
        text = out['explanation']
        source = (json.dumps(finding, ensure_ascii=False) + json.dumps(rule, ensure_ascii=False)).lower()
        fails = set()
        if any(m.group(0).lower() not in source for m in la._FOREIGN_SCRIPT.finditer(text)) or la._REPETITION.search(text):
            fails.add('garbled')
        names = ['currency', 'relative_time', 'clinical_fraud']
        for (pat, _), name in zip(la._UNGROUNDED, names):
            if any(m.group(0).lower() not in source for m in pat.finditer(text)):
                fails.add(name)
        for m in la._VALIDITY.finditer(text):
            if not (m.group(0).lower() in source or la._HEDGE.search(text[max(0, m.start() - 45):m.start()])):
                fails.add('validity')
        return fails

    for f in sorted((ROOT / 'experiments' / 'raw').glob('*.jsonl')):
        for line in f.read_text(encoding='utf-8').splitlines():
            r = json.loads(line)
            if r.get('type') != 'call' or r.get('case_id') not in cases:
                continue
            case = cases[r['case_id']]
            finding, rule = case['finding'], case['rule']
            for raw in r.get('raw_replies') or []:
                try:
                    out = _parse_reply(raw)
                except Exception:
                    unparse += 1
                    continue
                if not isinstance(out, dict):
                    unparse += 1
                    continue
                n += 1
                fails = set()
                try:
                    la.validate_explanation(copy.deepcopy(out), finding)
                except Exception:
                    # would the repair have rescued it?
                    try:
                        la.take_citation_repairs()
                        rep = la.repair_citations(copy.deepcopy(out), finding)
                        la.validate_explanation(rep, finding)
                        repair_rescued += 1
                        out = rep
                    except Exception:
                        fails.add('schema')
                        out = None
                if out is not None and isinstance(out.get('explanation'), str):
                    fails |= grounding_failures(out, finding, rule)
                # equivalence with production code on the same reply
                prod_ok = True
                try:
                    la.take_citation_repairs()
                    o2 = la.check_grounding(la.validate_explanation(la.repair_citations(copy.deepcopy(_parse_reply(raw)), finding), finding), finding, rule)
                except Exception:
                    prod_ok = False
                if prod_ok != (not fails):
                    mismatch += 1
                if fails:
                    any_reject += 1
                    for k in fails:
                        rejected_by[k] += 1
                        if len(examples[k]) < 2:
                            examples[k].append({'case': r['case_id'], 'text': (out or {}).get('explanation', raw)[:160] if out else raw[:160]})
                    if len(fails) == 1:
                        only_by[next(iter(fails))] += 1
    res = {'experiment': 'ablation', 'parsed_replies': n, 'unparseable_replies': unparse,
           'rejected_by_any_layer': any_reject, 'rejected_by_layer': rejected_by,
           'rejected_only_by_this_layer': only_by, 'rescued_by_citation_repair': repair_rescued,
           'mismatch_with_production_code': mismatch, 'examples': examples}
    save('ablation', res)
    return res


# ---------------------------------------------------------------- AI explanation vs the engine's own sentence
def aivstemplate():
    """Same scoring functions as the E10b decision (scripts/analyze_experiments.py), applied to (a) the final AI arm's live answers
    and (b) the template baselines, on the same 12 unseen cases. The 'useful' metric is known to reward echoing the template
    (SPECS 11.8), so it is reported but not leaned on."""
    sys.path.insert(0, str(ROOT / 'scripts'))
    import analyze_experiments as ae
    calls, _, _ = ae.load('e10b')
    arm = 'Mistral-Nemo-Instruct-2407|T0|p1|guided3|gate'
    ai = [r for r in calls if r['cfg_id'] == arm]
    case_ids = sorted({r['case_id'] for r in ai})

    def rate(recs, fn):
        return round(100.0 * sum(1 for r in recs if fn(r)) / len(recs), 1) if recs else None

    def template(with_action):
        out = []
        for cid in case_ids:
            f = ae.CASES[cid]['finding']
            text = f['explanation'] + (' ' + f['corrective_action'] if with_action else '')
            out.append({'case_id': cid, 'outcome': 'live', 'omitted_engine_reasons': [], 'explanation': text, 'raw_replies': []})
        return out

    live = [r for r in ai if r['outcome'] == 'live']
    arms = {'ai_live_answers': live, 'template_explanation_only': template(False),
            'template_plus_corrective_action_field': template(True)}
    res = {'experiment': 'aivstemplate', 'cases': len(case_ids), 'ai_live_answers_n': len(live),
           'ai_calls_rejected_to_template': len([r for r in ai if r['outcome'] != 'live']), 'metrics_percent': {}}
    for name, recs in arms.items():
        res['metrics_percent'][name] = {
            'states_corrective_action': rate(recs, ae.covers_action),
            'cites_a_value_from_the_evidence': rate(recs, ae.cites_observed_value),
            'useful_(biased_toward_template)': rate(recs, ae.is_useful),
            'mean_words': round(sum(len(r['explanation'].split()) for r in recs) / len(recs), 1)}
    save('aivstemplate', res)
    return res


# ---------------------------------------------------------------- precedence order vs the answer key
def precedence(n_generated=5000, seed=20260930):
    """Why FAIL > UNABLE_TO_ASSESS > NOT_APPLICABLE > PASS: score every order against (a) the organisers' answer key on the
    400 development claims and (b) the independent oracle on generated claims, where overlapping outcomes do occur."""
    import itertools
    sys.path.insert(0, str(ROOT / 'tests'))
    import oracle
    from claim_gen import random_claim
    from engine_core import validate_transport
    cfg = config(ROOT)
    pack = oracle.load_rules_pack(ROOT)
    claims = load_claims(400)
    gold = {}
    for line in (ROOT / 'data' / 'development' / 'expected_results.jsonl').read_text(encoding='utf-8').splitlines():
        if line.strip():
            g = json.loads(line)
            gold[(g['claim_id'], g['rule_id'])] = g['status']
    rng = random.Random(seed)
    generated = []
    while len(generated) < n_generated:
        c = random_claim(rng)
        try:
            validate_transport(c)
        except Exception:
            continue
        generated.append((c, oracle.evaluate(c, pack)))
    original = list(yara_engine.PRECEDENCE)
    out = {}
    try:
        for order in itertools.permutations(original):
            yara_engine.PRECEDENCE[:] = list(order)
            key_wrong = key_total = 0
            for c in claims:
                for r in yara_engine.evaluate(c, cfg):
                    k = (r['claim_id'], r['rule_id'])
                    if k in gold:
                        key_total += 1
                        key_wrong += r['status'] != gold[k]
            or_wrong = or_total = 0
            for c, want in generated:
                got = {r['rule_id']: r['status'] for r in yara_engine.evaluate(c, cfg)}
                for rid in want:
                    or_total += 1
                    or_wrong += got[rid] != want[rid]
            out[' > '.join(order)] = {'vs_answer_key': {'checked': key_total, 'disagree': key_wrong},
                                      'vs_oracle_on_generated': {'checked': or_total, 'disagree': or_wrong}}
    finally:
        yara_engine.PRECEDENCE[:] = original
    res = {'experiment': 'precedence', 'dev_claims': len(claims), 'generated_claims': n_generated, 'orders': out}
    save('precedence', res)
    return res


# ---------------------------------------------------------------- load
def load():
    import statistics
    import time
    cfg = config(ROOT)
    base = load_claims(600)
    res = {'experiment': 'load', 'engine': {}}
    for n in (1000, 5000, 20000):
        claims = [base[i % len(base)] for i in range(n)]
        t = time.perf_counter()
        for c in claims:
            yara_engine.evaluate(c, cfg)
        dt = time.perf_counter() - t
        res['engine'][n] = {'seconds': round(dt, 2), 'claims_per_s': round(n / dt, 1)}
    d = tempfile.mkdtemp()
    try:
        log = audit_log.AuditLog(Path(d) / 'a.jsonl')
        events = [{'event_type': 'rule_check', 'claim_id': f'CG-{i}', 'rule_id': 'R001', 'status': 'PASS'} for i in range(2000)]
        t = time.perf_counter()
        for i in range(0, len(events), 15):  # one claim's 15 checks per append, like a real run
            log._write(events[i:i + 15])
        dt = time.perf_counter() - t
        res['audit_append'] = {'events': len(events), 'seconds': round(dt, 2), 'events_per_s': round(len(events) / dt, 1)}
        t = time.perf_counter()
        audit_log.verify_with_anchor(Path(d) / 'a.jsonl')
        res['audit_verify_seconds_for_2000_events'] = round(time.perf_counter() - t, 3)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    lat = []
    for line in (ROOT / 'experiments' / 'raw' / 'e10b.jsonl').read_text(encoding='utf-8').splitlines():
        r = json.loads(line)
        if r.get('type') == 'call' and r['cfg_id'].endswith('|gate') and r['outcome'] == 'live':
            lat.append(r['latency_ms'] / 1000)
    res['ai_step_seconds'] = {'median': round(statistics.median(lat), 2), 'p95': round(sorted(lat)[int(0.95 * len(lat))], 2), 'calls': len(lat)}
    eng_ms = 1000 / res['engine'][20000]['claims_per_s']
    res['ai_median_over_engine_per_claim'] = round(res['ai_step_seconds']['median'] * 1000 / eng_ms)
    save('load', res)
    return res


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    runners = {'failclosed': failclosed, 'injection': injection, 'tamper': tamper, 'ablation': ablation, 'aivstemplate': aivstemplate, 'precedence': precedence, 'load': load}
    for name in (runners if which == 'all' else [which]):
        print(f'--- {name}')
        print(json.dumps(runners[name](), indent=2)[:6000])


if __name__ == '__main__':
    main()
