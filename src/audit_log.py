"""Audit log engine: a tamper-evident, append-only record of every check, AI
recommendation, system decision and human review action.

Design
------
- Same row format and hash function as the supplied src/audit.py
  ({sequence, recorded_at, previous_hash, event, hash}), so audit.verify()
  validates a log written here and vice versa. audit.py stays untouched.
- Reviewer decisions keep going through audit.append() (strict, unchanged).
  This module adds the *system* event kinds audit.py cannot express: ingestion,
  rule_check, ai_recommendation, system_decision, run_finished, recheck_run.
- The head hash and event count are also written to a separate anchor file
  (<log>.head.json). verify_with_anchor() then detects truncation and whole-log
  replacement, which a chain alone cannot.

What this is NOT
----------------
A hash chain is tamper-EVIDENT, not immutable: anyone with write access to the
file can rewrite the whole chain and the anchor together. Real immutability
needs storage the writer cannot alter (WORM / object-lock bucket, an append-only
database role) and/or an external timestamping service holding the head hash.
See docs/16_Audit_Log_Design.md.

Confidence: deterministic checks record confidence=null /
confidence_kind=not_probabilistic (docs/04_Rulebook.md). A model-reported score
would be recorded as 'uncalibrated'; the current explanation contract has none.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from audit import digest, verify

GENESIS = '0' * 64

# Every decision the system itself may take. None of them approves, denies or
# submits a claim (docs/01 scope boundaries): the only system decisions are
# routing decisions.
SYSTEM_DECISIONS = {'route_to_human_review', 'no_findings_for_review', 'quarantine_claim'}

_REQUIRED = {
    'ingestion': {'claim_id', 'source_format', 'outcome'},
    'run_started': {'run_id', 'claim_id', 'input_hash'},
    'rule_check': {'run_id', 'claim_id', 'rule_id', 'rule_version', 'status', 'severity',
                   'result_hash', 'confidence', 'confidence_kind', 'method'},
    'ai_recommendation': {'run_id', 'claim_id', 'rule_id', 'model', 'prompt_version',
                          'used_fallback', 'output_hash', 'confidence', 'confidence_kind'},
    'system_decision': {'run_id', 'claim_id', 'decision', 'reason'},
    'run_finished': {'run_id', 'claim_id', 'rule_pack_hash', 'tool_errors'},
    'recheck_run': {'claim_id', 'prior_run_id', 'new_run_id', 'prior_input_hash', 'new_input_hash'},
}


def _validate_system_event(event):
    kind = event.get('event_type')
    if kind not in _REQUIRED:
        raise ValueError(f'Unknown system event type: {kind!r}')
    missing = _REQUIRED[kind] - set(event)
    if missing:
        raise ValueError(f'{kind} event missing fields: {sorted(missing)}')
    if kind == 'system_decision' and event['decision'] not in SYSTEM_DECISIONS:
        raise ValueError(f"System decision {event['decision']!r} is not permitted")
    if kind in ('rule_check', 'ai_recommendation'):
        if event['confidence_kind'] == 'not_probabilistic' and event['confidence'] is not None:
            raise ValueError('not_probabilistic events must have null confidence')
        if event['confidence_kind'] not in ('not_probabilistic', 'uncalibrated', 'calibrated'):
            raise ValueError('Invalid confidence_kind')


class AuditLog:
    """Append-only chain writer. Loads and fully verifies the existing log once
    at open; later appends only need the tail state, so recording a whole run
    is one write rather than a re-verification per event."""

    def __init__(self, path):
        self.path = Path(path)
        self.anchor_path = self.path.with_name(self.path.name + '.head.json')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.head, self.count = verify(self.path)

    def append_system_events(self, events):
        for e in events:
            _validate_system_event(e)
        return self._write(events)

    def append_review_decisions(self, events):
        """Human decisions: delegate validation to the supplied audit.append()
        rules, then re-sync tail state. Kept strict on purpose."""
        from audit import append
        self.head, self.count = append(self.path, events)
        self._write_anchor()
        return self.head, self.count

    def _write(self, events):
        with self.path.open('a', encoding='utf-8') as f:
            for event in events:
                row = {'sequence': self.count + 1,
                       'recorded_at': datetime.now(timezone.utc).isoformat(),
                       'previous_hash': self.head, 'event': event}
                self.head = digest(row)
                f.write(json.dumps({**row, 'hash': self.head}, ensure_ascii=False) + '\n')
                self.count += 1
        self._write_anchor()
        return self.head, self.count

    def _write_anchor(self):
        self.anchor_path.write_text(json.dumps({
            'head': self.head, 'count': self.count,
            'written_at': datetime.now(timezone.utc).isoformat(),
            'note': 'Keep a copy of this file somewhere the log writer cannot modify.',
        }, indent=2), encoding='utf-8')


def verify_with_anchor(log_path, anchor_path=None):
    """Full chain verification plus comparison against the anchor. Returns
    (head, count). Raises ValueError on a broken chain, truncation, or a
    replaced log."""
    log_path = Path(log_path)
    anchor_path = Path(anchor_path) if anchor_path else log_path.with_name(log_path.name + '.head.json')
    head, count = verify(log_path)
    if not anchor_path.exists():
        raise ValueError('No anchor file: chain is internally consistent but cannot be checked against truncation')
    anchor = json.loads(anchor_path.read_text(encoding='utf-8'))
    if count < anchor['count']:
        raise ValueError(f"Log truncated: {count} events, anchor recorded {anchor['count']}")
    rows = [json.loads(l) for l in log_path.read_text(encoding='utf-8').splitlines() if l.strip()]
    if rows[anchor['count'] - 1]['hash'] != anchor['head']:
        raise ValueError('Log replaced: hash at anchored position differs from the anchor')
    return head, count


def events_for_run(claim, rule_results, ai_explanations, run_trace, source_format='normalized_json',
                   ingestion_report=None):
    """Translate one review_package() outcome into audit events. Rule results
    are recorded by content hash plus the fields a reviewer needs to see; the
    full records remain in the results file the hash refers to."""
    claim_id = run_trace['claim_id']
    run_id = run_trace['run_id']
    if rule_results is None:
        return [
            {'event_type': 'ingestion', 'claim_id': claim_id, 'source_format': source_format,
             'outcome': 'quarantined', 'error': run_trace.get('ingestion_error')},
            {'event_type': 'system_decision', 'run_id': run_id, 'claim_id': claim_id,
             'decision': 'quarantine_claim', 'reason': run_trace.get('ingestion_error', 'ingestion failed')},
        ]
    report = ingestion_report or {}
    events = [
        {'event_type': 'ingestion', 'claim_id': claim_id, 'source_format': source_format, 'outcome': 'accepted',
         'warnings': report.get('warnings', []), 'not_carried_by_source': report.get('not_carried_by_fhir', [])},
        {'event_type': 'run_started', 'run_id': run_id, 'claim_id': claim_id,
         'input_hash': run_trace['input_hash'], 'started_at': run_trace['started_at']},
    ]
    for r in rule_results:
        events.append({
            'event_type': 'rule_check', 'run_id': run_id, 'claim_id': claim_id,
            'rule_id': r['rule_id'], 'rule_version': r['rule_version'], 'status': r['status'],
            'severity': r['severity'], 'affected_line_ids': r['affected_line_ids'],
            'result_hash': digest(r), 'confidence': r['confidence'],
            'confidence_kind': r['confidence_kind'], 'method': r['method'],
        })
    for a in ai_explanations:
        events.append({
            'event_type': 'ai_recommendation', 'run_id': run_id, 'claim_id': claim_id,
            'rule_id': a['rule_id'], 'model': run_trace['model'] if not a['used_fallback'] else 'deterministic-template',
            'prompt_version': run_trace['prompt_version'], 'used_fallback': a['used_fallback'],
            'error': a['error'], 'latency_ms': a['latency_ms'], 'usage': a['usage'],
            'output_hash': digest(a['output']), 'explanation': a['output']['explanation'],
            # The explanation contract carries no score; deterministic-derived text
            # is not a probability. Never fabricate one.
            'confidence': None, 'confidence_kind': 'not_probabilistic',
        })
    needs_review = [r for r in rule_results if r['requires_human_review']]
    events.append({
        'event_type': 'system_decision', 'run_id': run_id, 'claim_id': claim_id,
        'decision': 'route_to_human_review' if needs_review else 'no_findings_for_review',
        'reason': (f"{len(needs_review)} finding(s) require human review: "
                   + ', '.join(f"{r['rule_id']}={r['status']}" for r in needs_review)) if needs_review
                  else 'No FAIL or UNABLE_TO_ASSESS findings. This is not an approval.',
    })
    events.append({
        'event_type': 'run_finished', 'run_id': run_id, 'claim_id': claim_id,
        'rule_pack_hash': run_trace['rule_pack_hash'], 'rule_versions': run_trace['rule_versions'],
        'tool_errors': run_trace['tool_errors'], 'finished_at': run_trace['finished_at'],
    })
    return events


def events_for_quarantined_record(source_ref, source_format, error, claim_id='UNKNOWN'):
    """A record that never became a claim (bad JSON, unmappable bundle, failed
    transport contract). It is logged and routed to quarantine, never dropped."""
    return [
        {'event_type': 'ingestion', 'claim_id': claim_id, 'source_format': source_format,
         'outcome': 'quarantined', 'source_ref': source_ref, 'error': error},
        {'event_type': 'system_decision', 'run_id': None, 'claim_id': claim_id,
         'decision': 'quarantine_claim', 'reason': error},
    ]
