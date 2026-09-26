"""Compile rules/core.yar, scan a claim's facts blob, resolve precedence, assemble results."""
import hashlib
import logging
import threading
from pathlib import Path

import yara_x

from engine_core import pointer
from facts_extractor import (
    r001_details, r002_details, r003_details, r004_details, r005_details,
    r006_details, r007_details, r008_details, r009_details, r010_details,
    r011_details, r012_details, r013_details, r014_details, r015_details, rule_view,
)

logger = logging.getLogger('yara_engine')

PACK_PATH = Path(__file__).resolve().parents[1] / 'rules' / 'core.yar'
PRECEDENCE = ['FAIL', 'UNABLE_TO_ASSESS', 'NOT_APPLICABLE', 'PASS']
# Every entry is called as fn(claim, cfg); rules that don't need cfg ignore it.
DETAIL_FUNCS = {
    'R001': lambda c, cfg: r001_details(c),
    'R002': lambda c, cfg: r002_details(c),
    'R003': lambda c, cfg: r003_details(c),
    'R004': lambda c, cfg: r004_details(c),
    'R005': r005_details,
    'R006': lambda c, cfg: r006_details(c),
    'R007': lambda c, cfg: r007_details(c),
    'R008': r008_details,
    'R009': r009_details,
    'R010': r010_details,
    'R011': r011_details,
    'R012': lambda c, cfg: r012_details(c),
    'R013': r013_details,
    'R014': r014_details,
    'R015': r015_details,
}

_compiled = None
_ENGINE_LOCK = threading.Lock()  # yara-x thread-safety is not assumed: compile and scan are serialized (~1 ms each)


class EngineError(Exception):
    pass


def compiled_rules():
    global _compiled
    with _ENGINE_LOCK:
        if _compiled is None:
            _compiled = yara_x.compile(PACK_PATH.read_text(encoding='utf-8'))
        return _compiled


def pack_hash():
    return hashlib.sha256(PACK_PATH.read_bytes()).hexdigest()


def engine_code_hash():
    """Identifies the code that produced a result: the rule pack plus the two modules that feed and assemble it. rule_version
    is the rulebook's (not ours to bump), so this is what tells two builds of the engine apart in an audit trace."""
    here = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for path in (PACK_PATH, here / 'facts_extractor.py', here / 'yara_engine.py'):
        # splitlines() makes the digest the same whether git checked the file out with LF or CRLF
        h.update(b'|'.join([path.name.encode()] + path.read_bytes().splitlines()))
    return h.hexdigest()


def _safe_evidence(c, paths):
    """Evidence = direct pointer lookups on the ORIGINAL claim. A path that cannot be resolved is
    dropped rather than crashing; if none resolve, /claim_id (always present) keeps the result
    scorable, because the scorer rejects empty evidence."""
    out = []
    for p in dict.fromkeys(paths):
        try:
            out.append({'path': p, 'value': pointer(c, p)})
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return out or [{'path': '/claim_id', 'value': c['claim_id']}]


def evaluate(c, cfg, tool_errors=None):
    """Evaluate all rules for one claim. Never raises for a claim that has an id and a rule
    catalogue: an unexpected error inside ONE rule turns that rule's result into UNABLE_TO_ASSESS
    (human review required, never PASS), the other rules are unaffected, and the error text is
    appended to `tool_errors` (kept out of the result record, which is schema-exact).
    EngineError (pack and extractor out of sync) still propagates: that is a build defect."""
    detail_funcs = DETAIL_FUNCS
    view = rule_view(c)
    details, crashed = {}, {}
    for rid, fn in detail_funcs.items():
        try:
            details[rid] = fn(view, cfg)
        except Exception as e:  # noqa: BLE001 - isolation is the point
            crashed[rid] = f'{type(e).__name__}: {e}'
            logger.warning('rule %s crashed on %r, treating as UNABLE_TO_ASSESS: %r', rid, c.get('claim_id'), crashed[rid])
            if tool_errors is not None:
                tool_errors.append(f'{rid}: engine exception {crashed[rid]}')
    blob = '\n'.join(fact for d in details.values() for fact in d['facts']) + '\n'
    rules = compiled_rules()
    with _ENGINE_LOCK:
        scan = rules.scan(blob.encode('utf-8'))
        matched = [(dict(rule.metadata)['rule_id'], dict(rule.metadata)['outcome']) for rule in scan.matching_rules]
    by_rule = {}
    for rid, outcome in matched:
        by_rule.setdefault(rid, set()).add(outcome)
    rule_defs = {r['rule_id']: r for r in cfg['rules']}
    results = []
    for rule_id in detail_funcs:
        r = rule_defs[rule_id]
        if rule_id in crashed:
            status, d = 'UNABLE_TO_ASSESS', {
                'line_ids': [], 'evidence_paths': ['/claim_id'],
                'message': 'An internal error prevented this check; it is treated as unable to assess.'}
        else:
            outcomes = by_rule.get(rule_id, set())
            if not outcomes:
                raise EngineError(f'{rule_id} produced no outcome - extractor and rule pack are out of sync')
            status = next(o for o in PRECEDENCE if o in outcomes)
            d = details[rule_id]
        results.append({
            'claim_id': c['claim_id'],
            'rule_id': rule_id,
            'rule_version': r['version'],
            'status': status,
            'severity': r['severity'],
            'affected_line_ids': d['line_ids'],
            'evidence': _safe_evidence(c, d['evidence_paths']),
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


def fail_closed_results(c, cfg):
    """15 UNABLE_TO_ASSESS results for a claim that could not be evaluated at all (it failed the
    transport contract). Never PASS. Evidence is /claim_id, the only path guaranteed to exist."""
    return [{
        'claim_id': c['claim_id'], 'rule_id': r['rule_id'], 'rule_version': r['version'],
        'status': 'UNABLE_TO_ASSESS', 'severity': r['severity'], 'affected_line_ids': [],
        'evidence': [{'path': '/claim_id', 'value': c['claim_id']}], 'rule_source': r['source'],
        'explanation': 'The claim failed the input contract, so this check could not be performed.',
        'corrective_action': r['corrective_action'], 'confidence': None,
        'confidence_kind': 'not_probabilistic', 'requires_human_review': True,
        'method': 'deterministic', 'review_status': 'unreviewed',
    } for r in sorted(cfg['rules'], key=lambda r: r['rule_id'])]
