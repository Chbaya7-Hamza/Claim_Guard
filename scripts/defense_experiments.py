"""Experiments that back technical decisions (docs/27). Each one has a baseline or a control that
could make the decision look wrong, and every result is written to outputs/defense/ as recorded.

    python scripts/defense_experiments.py failclosed    # a crash in each of the 15 rules
    python scripts/defense_experiments.py injection     # forged facts, with and without percent-encoding
    python scripts/defense_experiments.py tamper        # audit-log tampering vs chain / +anchor / strict / +HMAC key
    python scripts/defense_experiments.py ablation      # each validation guard replayed on recorded raw replies
    python scripts/defense_experiments.py aivstemplate  # AI explanations vs the engine's own sentence
    python scripts/defense_experiments.py precedence    # every status-precedence order vs the key and the oracle
    python scripts/defense_experiments.py load          # engine, audit append and AI-step timings
    python scripts/defense_experiments.py ingestformats # CSV and FHIR vs JSONL: same verdicts, silent passes
    python scripts/defense_experiments.py quarantine    # damaged records vs two naive readers
    python scripts/defense_experiments.py limits        # do the prompt limits bite real data, and stop hostile data
    python scripts/defense_experiments.py workers       # worker count, from the recorded E4 data
    python scripts/defense_experiments.py review        # decision validation, batch atomicity, recheck
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
    forged = trials = errors = 0
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
                        errors += 1  # a crash is reported, never counted as "resisted"
                        continue
                    flips = {k for k in base if got[k] != base[k]} - legit
                    if flips:
                        forged += 1
                        if len(examples) < 5:
                            examples.append({'claim_id': c['claim_id'], 'field': field, 'payload': shape[:80],
                                             'rules_flipped': sorted(flips)})
    return {'trials': trials, 'forged_outcomes': forged, 'engine_errors': errors, 'examples': examples}


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


@attack
def rewrite_all_and_anchor_with_stolen_key(p, key):
    """An attacker who holds AUDIT_ANCHOR_KEY signs a forged anchor correctly. Only meaningful in the keyed configuration; in
    the unkeyed one it is the same as rewriting without a key."""
    r = _rows(p)
    r[10]['event']['status'] = 'FAIL'
    r = _rechain(r, 10)
    _write_rows(p, r)
    _write_anchor(p, r, mac_key=key)


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
    try:
        return _tamper()
    finally:
        os.environ.pop(audit_log.ANCHOR_KEY_ENV, None)  # never leave the experiment's key in the process environment


def _tamper():
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
    layers = ['schema', 'currency', 'relative_time', 'clinical_fraud', 'approval', 'validity', 'garbled']
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
        names = ['currency', 'relative_time', 'clinical_fraud', 'approval']
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


# ---------------------------------------------------------------- ingestion formats
def ingestformats():
    """Do the three input shapes reach the same verdicts? JSONL is the reference; CSV folder and FHIR bundle are compared with it
    claim by claim, field by field and rule by rule. A result where a lossy path says PASS but the full data does not is a
    silent pass and is counted separately."""
    import ingest as ing
    cfg = config(ROOT)
    out = {'experiment': 'ingestformats', 'splits': {}}
    for split in ('development', 'validation', 'stress'):
        base = ROOT / 'data' / split
        ref = {c['claim_id']: c for c in (x.claim for x in ing.ingest(base / 'claims.jsonl'))}
        ref_status = {cid: {r['rule_id']: r['status'] for r in yara_engine.evaluate(c, cfg)} for cid, c in ref.items()}
        row = {'reference_claims': len(ref)}
        for label, path in (('csv_folder', base / 'csv'), ('fhir_bundle', base / 'fhir_bundles.jsonl')):
            items = list(ing.ingest(path))
            accepted = [i.claim for i in items if i.accepted]
            identical = verdict_same = results = silent = 0
            diffs = {}
            for c in accepted:
                identical += c == ref[c['claim_id']]
                got = {r['rule_id']: r['status'] for r in yara_engine.evaluate(c, cfg)}
                for rid, st in ref_status[c['claim_id']].items():
                    results += 1
                    if got[rid] == st:
                        verdict_same += 1
                    else:
                        diffs[f'{rid}: {st} -> {got[rid]}'] = diffs.get(f'{rid}: {st} -> {got[rid]}', 0) + 1
                        silent += got[rid] == 'PASS'
            row[label] = {'records': len(items), 'accepted': len(accepted), 'quarantined': len(items) - len(accepted),
                          'claims_field_identical_to_jsonl': identical, 'results_compared': results,
                          'verdict_agreement_percent': round(100.0 * verdict_same / results, 2) if results else None,
                          'silent_passes': silent, 'differences': diffs}
        out['splits'][split] = row
    save('ingestformats', out)
    return out


# ---------------------------------------------------------------- quarantine
def _corrupt_lines(valid_claims):
    """Ten kinds of damaged record, each as a raw line (bytes) so invalid UTF-8 can be included."""
    good = json.dumps(valid_claims[0])
    bad = []
    bad.append(('not_json', b'this is not json'))
    bad.append(('truncated_json', good[:len(good) // 2].encode()))
    bad.append(('null_line', b'null'))
    bad.append(('number_line', b'12345'))
    bad.append(('array_line', b'[1, 2, 3]'))
    bad.append(('invalid_utf8', b'{"claim_id": "\xff\xfe"}'))
    c = dict(valid_claims[1]); del c['currency']
    bad.append(('missing_required_key', json.dumps(c).encode()))
    c = dict(valid_claims[2]); c['unexpected'] = 1
    bad.append(('unknown_key', json.dumps(c).encode()))
    c = dict(valid_claims[3]); c['total_amount'] = 'not a number'
    bad.append(('wrong_type_amount', json.dumps(c).encode()))
    bad.append(('deep_nesting', b'[' * 50000 + b']' * 50000))
    return bad


def quarantine(n_valid=100, copies=3):
    """A file with valid claims and damaged records interleaved. Compare ClaimGuard's ingestion with two naive readers: one that
    stops at the first bad line, one that skips bad lines without a trace."""
    import ingest as ing
    cfg = config(ROOT)
    valid = load_claims(n_valid)
    bad = _corrupt_lines(valid) * copies
    lines, kinds, rng = [], [], random.Random(7)
    slots = sorted(rng.sample(range(len(valid) + len(bad)), len(bad)))
    vi = bi = 0
    for pos in range(len(valid) + len(bad)):
        if bi < len(bad) and pos == slots[bi]:
            lines.append(bad[bi][1]); kinds.append(bad[bi][0]); bi += 1
        else:
            lines.append(json.dumps(valid[vi]).encode()); kinds.append('valid'); vi += 1
    d = tempfile.mkdtemp()
    try:
        path = Path(d) / 'mixed.jsonl'
        path.write_bytes(b'\n'.join(lines) + b'\n')
        items = list(ing.ingest(path))
        accepted = [i.claim for i in items if i.accepted]
        quarantined = [i for i in items if not i.accepted]
        clean = {c['claim_id']: {r['rule_id']: r['status'] for r in yara_engine.evaluate(c, cfg)} for c in valid}
        # a wrong-typed amount is accepted by design and read as unknown by the rules; measure that separately
        soft = [c for c in accepted if isinstance(c.get('total_amount'), str)]
        sound = [c for c in accepted if not isinstance(c.get('total_amount'), str)]
        same = sum(1 for c in sound if {r['rule_id']: r['status'] for r in yara_engine.evaluate(c, cfg)} == clean[c['claim_id']])
        soft_status = [{r['rule_id']: r['status'] for r in yara_engine.evaluate(c, cfg)} for c in soft]
        # R012 (claim total equals the line amounts) is the rule that depends on total_amount; R001 does not look at it
        soft_summary = {'records': len(soft), 'R012_status': sorted({x['R012'] for x in soft_status}),
                        'any_PASS_on_R012': any(x['R012'] == 'PASS' for x in soft_status)}
        reasons = {}
        for i in quarantined:
            reasons[i.error.split(':')[0]] = reasons.get(i.error.split(':')[0], 0) + 1
        # naive reader 1: stops at the first line that does not parse
        processed_before_crash = 0
        for ln in lines:
            try:
                json.loads(ln)
                processed_before_crash += 1
            except Exception:
                break
        # naive reader 2: skips what does not parse, records nothing
        parsed = 0
        for ln in lines:
            try:
                json.loads(ln)
                parsed += 1
            except Exception:
                pass
    finally:
        shutil.rmtree(d, ignore_errors=True)
    res = {'experiment': 'quarantine', 'valid_records': len(valid), 'damaged_records': len(bad),
           'damage_kinds': sorted({k for k, _ in bad}),
           'claimguard': {'accepted': len(accepted), 'quarantined': len(quarantined), 'quarantine_reasons': reasons,
                          'every_record_accounted_for': len(accepted) + len(quarantined) == len(lines),
                          'sound_claims_with_unchanged_verdicts': f'{same} of {len(sound)}',
                          'wrong_typed_amount_records_accepted_by_design': soft_summary,
                          'quarantined_records_that_reached_the_rules': len([i for i in quarantined if i.claim is not None])},
           'naive_stop_at_first_error': {'valid_claims_processed_before_stopping': processed_before_crash,
                                         'valid_claims_never_processed': len(valid) - min(processed_before_crash, len(valid))},
           'naive_skip_silently': {'records_dropped_with_no_record_of_why': len(lines) - parsed},
           'note': 'parse-only baselines: they do not validate claims, so they understate what a naive reader would miss.'}
    save('quarantine', res)
    return res


# ---------------------------------------------------------------- input limits
def limits():
    """Do the prompt size limits bite real data, and do they stop hostile data? Measured on every finding that would be sent
    to the model in the three public splits, then on a hostile 5,000-line claim."""
    import llm_adapter as la
    cfg = config(ROOT)
    rules = {r['rule_id']: r for r in cfg['rules']}
    lengths, longest_value, notes_len = [], 0, []
    for split in ('development', 'validation', 'stress'):
        for c in load_jsonl_split(split):
            notes_len.append(len(str(c.get('notes') or '')))
            for r in yara_engine.evaluate(c, cfg):
                if r['status'] in ('FAIL', 'UNABLE_TO_ASSESS'):
                    lengths.append(len(la.build_prompt(r, rules[r['rule_id']])))
                    for e in r['evidence']:
                        longest_value = max(longest_value, len(json.dumps(e['value'], ensure_ascii=False)))
    lengths.sort()
    pct = lambda q: lengths[min(len(lengths) - 1, int(q * len(lengths)))]
    # hostile claim: thousands of lines, every one a finding
    big = copy.deepcopy(load_claims(1)[0])
    line = big['lines'][0]
    big['lines'] = [{**line, 'line_id': f'L{i}', 'quantity': 0} for i in range(5000)]
    hostile = [r for r in yara_engine.evaluate(big, cfg) if r['status'] == 'FAIL']
    hostile_len = len(la.build_prompt(hostile[0], rules[hostile[0]['rule_id']])) if False else None
    results = {'finding_prompts_measured': len(lengths), 'prompt_chars': {'median': pct(0.5), 'p99': pct(0.99), 'max': lengths[-1]},
               'limit_chars': la.MAX_PROMPT_CHARS, 'findings_over_the_prompt_limit': sum(1 for n in lengths if n > la.MAX_PROMPT_CHARS),
               'longest_evidence_value_chars': longest_value, 'per_value_limit_chars': la.MAX_VALUE_CHARS,
               'values_over_the_per_value_limit': 'see longest_evidence_value_chars',
               'longest_note_chars': max(notes_len), 'note_limit_chars': la.MAX_NOTE_CHARS}
    failed_closed = None
    for f in hostile:
        try:
            n = len(la.build_prompt(f, rules[f['rule_id']]))
            hostile_len = n
        except ValueError as e:
            failed_closed = str(e)
            break
    results['hostile_5000_line_claim'] = {'fail_findings': len(hostile), 'first_prompt_chars_if_built': hostile_len,
                                          'failed_closed_to_template': failed_closed}
    res = {'experiment': 'limits', **results}
    save('limits', res)
    return res


def load_jsonl_split(split):
    return [c for c in load_claims_from(ROOT / 'data' / split / 'claims.jsonl')]


def load_claims_from(path):
    out = []
    for _, line, err in read_lines(path):
        if err:
            continue
        c, perr = parse_json(line)
        if not perr:
            out.append(c)
    return out


# ---------------------------------------------------------------- worker count (recorded E4)
def workers():
    """Throughput and quality by worker count, from the recorded E4 concurrency experiment (experiments/raw/e4.jsonl)."""
    import statistics
    rows = [json.loads(l) for l in (ROOT / 'experiments' / 'raw' / 'e4.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    table = {}
    for b in (r for r in rows if r['type'] == 'batch'):
        model = b['cfg_id'].split('|')[0]
        calls = [r for r in rows if r['type'] == 'call' and r['cfg_id'] == b['cfg_id']]
        lat = sorted(r['latency_ms'] / 1000 for r in calls)
        table.setdefault(model, {})[b['workers']] = {
            'calls': b['calls'], 'wall_seconds': b['wall_s'], 'calls_per_second': round(b['calls'] / b['wall_s'], 3),
            'live': sum(1 for r in calls if r['outcome'] == 'live'), 'rejected': sum(1 for r in calls if r['outcome'] != 'live'),
            'latency_p50_s': round(statistics.median(lat), 2), 'latency_p95_s': round(lat[int(0.95 * len(lat))], 2)}
    res = {'experiment': 'workers', 'source': 'experiments/raw/e4.jsonl (36 calls per level)', 'by_model': table}
    save('workers', res)
    return res


def _count_lines(path):
    with open(path, encoding='utf-8') as f:
        return sum(1 for _ in f)


# ---------------------------------------------------------------- review workflow
def review(n_claims=40):
    """Decision validation, batch atomicity, and recheck, each against an adversarial battery."""
    import review_workflow as rw
    from llm_adapter import MockExplanationProvider
    cfg = config(ROOT)
    claims = load_claims(n_claims)
    provider = MockExplanationProvider()
    d = tempfile.mkdtemp()
    try:
        log = audit_log.AuditLog(Path(d) / 'review.jsonl')
        runs = {}
        for c in claims:
            res, ai, trace = audit_log.audited_review(log, copy.deepcopy(c), cfg, provider=provider)
            runs[c['claim_id']] = (c, res, trace)
        all_results = [r for _, res, _ in runs.values() for r in res]
        findings = rw.index_findings(all_results)
        reviewable = [r for r in all_results if r['status'] in rw.REVIEWABLE]
        passes = [r for r in all_results if r['status'] == 'PASS']
        now = '2026-09-30T12:00:00+00:00'

        def good(r, action='confirm_issue'):
            return {'claim_id': r['claim_id'], 'rule_id': r['rule_id'], 'action': action, 'actor': 'tester',
                    'reason': 'because', 'created_at': now, 'original_status': r['status']}

        def accepted(dec):
            try:
                rw.validate_decision(dec, findings)
                return True
            except rw.DecisionError:
                return False

        valid_ok = sum(accepted(good(r, a)) for r in reviewable for a in ('confirm_issue', 'dismiss_with_reason',
                                                                        'request_information', 'mark_corrected_for_recheck'))
        valid_total = len(reviewable) * 4
        mutations = {
            'empty_reason': lambda r: {**good(r), 'reason': '   '},
            'blank_actor': lambda r: {**good(r), 'actor': ''},
            'unknown_action': lambda r: {**good(r), 'action': 'auto_approve'},
            'extra_field': lambda r: {**good(r), 'confidence': 0.99},
            'wrong_original_status': lambda r: {**good(r), 'original_status': 'PASS'},
            'unknown_claim': lambda r: {**good(r), 'claim_id': 'CG-DOES-NOT-EXIST'},
            'bad_timestamp': lambda r: {**good(r), 'created_at': 'yesterday'},
            'missing_field': lambda r: {k: v for k, v in good(r).items() if k != 'reason'},
        }
        mut = {}
        for name, fn in mutations.items():
            wrong = sum(accepted(fn(r)) for r in reviewable)
            mut[name] = {'tried': len(reviewable), 'wrongly_accepted': wrong}
        pass_finding = {'tried': len(passes), 'wrongly_accepted': sum(accepted({**good(r), 'original_status': 'PASS'}) for r in passes)}
        # batch atomicity
        before = _count_lines(log.path)
        batch = [good(r) for r in reviewable[:5]] + [{**good(reviewable[5]), 'reason': ''}]
        try:
            rw.apply_decisions(log, batch, all_results)
            rejected_batch = False
        except rw.DecisionError:
            rejected_batch = True
        after = _count_lines(log.path)
        # recheck: originals untouched, new run linked, a still-failing finding goes back to unreviewed
        originals = {cid: copy.deepcopy(c) for cid, (c, _, _) in runs.items()}
        prior_results = {cid: copy.deepcopy(res) for cid, (_, res, _) in runs.items()}
        rechecked = untouched = linked = back_to_unreviewed = fixed = fixable = 0
        for cid, (c, res, trace) in runs.items():
            fails = [r for r in res if r['status'] == 'FAIL']
            if not fails:
                continue
            target = fails[0]
            corrected = copy.deepcopy(c)
            corrected['notes'] = (corrected.get('notes') or '') + ' [reviewer note: checked with provider]'
            rw.apply_decisions(log, [good(target, 'confirm_issue')], res)
            new_res, _, new_trace, changes = rw.recheck(log, c, corrected, res, trace, cfg, [target['rule_id']],
                                                        'tester', 'rechecked', provider=provider)
            rechecked += 1
            untouched += (c == originals[cid]) and (res == prior_results[cid])
            linked += new_trace['run_id'] != trace['run_id']
            state = rw.review_state(new_res, log.path)
            back_to_unreviewed += (changes[target['rule_id']][1] == 'FAIL' and
                                   state.get((cid, target['rule_id'])) == 'unreviewed')
            if target['rule_id'] == 'R015':
                fixable += 1
                fixed_claim = copy.deepcopy(c)
                fixed_claim['currency'] = 'SAR'
                _, _, t2, ch2 = rw.recheck(log, c, fixed_claim, res, trace, cfg, ['R015'], 'tester', 'currency corrected',
                                           provider=provider)
                fixed += ch2['R015'][1] == 'PASS'
        verify = audit_log.verify_with_anchor(log.path, strict=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    res = {'experiment': 'review', 'claims': len(claims), 'reviewable_findings': len(reviewable),
           'valid_decisions_accepted': {'accepted': valid_ok, 'of': valid_total},
           'invalid_decisions_wrongly_accepted': mut, 'decision_on_a_PASS_finding': pass_finding,
           'batch_with_one_bad_decision': {'rejected_whole_batch': rejected_batch, 'log_rows_before': before, 'log_rows_after': after},
           'recheck': {'claims_rechecked': rechecked, 'original_claim_and_results_untouched': untouched,
                       'new_run_id_differs': linked, 'still_failing_finding_back_to_unreviewed': back_to_unreviewed,
                       'currency_corrections_tried': fixable, 'currency_corrections_that_turned_R015_to_PASS': fixed},
           'audit_log_still_verifies_strict': True if verify else False}
    save('review', res)
    return res


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    runners = {'failclosed': failclosed, 'injection': injection, 'tamper': tamper, 'ablation': ablation, 'aivstemplate': aivstemplate, 'precedence': precedence, 'load': load,
               'ingestformats': ingestformats, 'quarantine': quarantine, 'limits': limits, 'workers': workers, 'review': review}
    for name in (runners if which == 'all' else [which]):
        print(f'--- {name}')
        print(json.dumps(runners[name](), indent=2)[:6000])


if __name__ == '__main__':
    main()
