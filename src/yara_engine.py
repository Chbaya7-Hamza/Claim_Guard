"""Compile rules/core.yar, scan a claim's facts blob, resolve precedence, assemble results."""
import hashlib
from pathlib import Path

import yara_x

from engine_core import pointer
from facts_extractor import r001_details, r003_details, r006_details

PACK_PATH = Path(__file__).resolve().parents[1] / 'rules' / 'core.yar'
PRECEDENCE = ['FAIL', 'UNABLE_TO_ASSESS', 'NOT_APPLICABLE', 'PASS']
DETAIL_FUNCS = {'R001': r001_details, 'R003': r003_details, 'R006': r006_details}

_compiled = None


class EngineError(Exception):
    pass


def compiled_rules():
    global _compiled
    if _compiled is None:
        _compiled = yara_x.compile(PACK_PATH.read_text(encoding='utf-8'))
    return _compiled


def pack_hash():
    return hashlib.sha256(PACK_PATH.read_bytes()).hexdigest()


def evaluate(c, cfg):
    detail_funcs = DETAIL_FUNCS
    details = {rid: fn(c) for rid, fn in detail_funcs.items()}
    blob = '\n'.join(fact for d in details.values() for fact in d['facts']) + '\n'
    scan = compiled_rules().scan(blob.encode('utf-8'))
    by_rule = {}
    for rule in scan.matching_rules:
        meta = dict(rule.metadata)
        by_rule.setdefault(meta['rule_id'], set()).add(meta['outcome'])
    rule_defs = {r['rule_id']: r for r in cfg['rules']}
    results = []
    for rule_id in detail_funcs:
        outcomes = by_rule.get(rule_id, set())
        if not outcomes:
            raise EngineError(f'{rule_id} produced no outcome - extractor and rule pack are out of sync')
        status = next(o for o in PRECEDENCE if o in outcomes)
        r = rule_defs[rule_id]
        d = details[rule_id]
        results.append({
            'claim_id': c['claim_id'],
            'rule_id': rule_id,
            'rule_version': r['version'],
            'status': status,
            'severity': r['severity'],
            'affected_line_ids': d['line_ids'],
            'evidence': [{'path': p, 'value': pointer(c, p)} for p in dict.fromkeys(d['evidence_paths'])],
            'rule_source': r['source'],
            'explanation': d['message'],
            'corrective_action': r['corrective_action'] if status in ('FAIL', 'UNABLE_TO_ASSESS') else '',
            'confidence': None,
            'confidence_kind': 'not_probabilistic',
            'requires_human_review': status in ('FAIL', 'UNABLE_TO_ASSESS'),
            'method': 'deterministic',
            'review_status': 'unreviewed',
        })
    return results
