"""Audit log engine: a tamper-evident, append-only record of every check, AI
recommendation, system decision and human review action.

Design
------
- Same row format and hash function as the supplied src/audit.py
  ({sequence, recorded_at, previous_hash, event, hash}), so audit.verify()
  validates a log written here and vice versa. audit.py stays untouched.
- Reviewer decisions keep going through audit.append() (strict, unchanged).
  This module adds the *system* event kinds audit.py cannot express.
- The head hash and event count are also written to a separate anchor file
  (<log>.head.json). verify_with_anchor() then detects truncation and whole-log
  replacement, which a chain alone cannot. Opening an existing log re-checks it
  against its anchor first.

Write-ahead ordering (what is recorded BEFORE the AI acts)
----------------------------------------------------------
audited_review() writes each stage to the log before the next stage runs:

    ingestion + run_started        input accepted
    rule_check x15                 the deterministic verdicts, before any AI call
    ai_request                     the question put to the AI: which finding, its
                                   verdict (violation_detected / cannot_determine),
                                   hashes of the finding and the exact prompt, and
                                   the action type -- written BEFORE the model call
    ai_recommendation | ai_failure the outcome, linked by request_id
    system_decision, run_finished

If a log write fails, the exception propagates and the AI is not called (a hook
failure aborts the run). verify_ai_ordering() re-checks this from the log alone.

AI action types
---------------
Every AI action is recorded as `human_escalation`: the model drafts an explanation and
the finding goes to a person. `auto_correct` (the AI changing a claim or a result) is not
a permitted value; an event claiming it is rejected at write time and by the verifier.

What this is NOT
----------------
A hash chain is tamper-EVIDENT, not immutable: anyone with write access to the
file can rewrite the whole chain and the anchor together. See
docs/16_Audit_Log_Design.md.

Confidence: deterministic checks record confidence=null /
confidence_kind=not_probabilistic (docs/04_Rulebook.md).
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
AI_ACTION_TYPES = {'human_escalation'}
FORBIDDEN_AI_ACTIONS = {'auto_correct'}

_REQUIRED = {
    'ingestion': {'claim_id', 'source_format', 'outcome'},
    'run_started': {'run_id', 'claim_id', 'input_hash'},
    'rule_check': {'run_id', 'claim_id', 'rule_id', 'rule_version', 'status', 'severity',
                   'result_hash', 'confidence', 'confidence_kind', 'method'},
    'ai_request': {'run_id', 'claim_id', 'rule_id', 'request_id', 'question', 'deterministic_status',
                   'verdict', 'requires_human_review', 'finding_hash', 'prompt_version', 'prompt_hash',
                   'action_type'},
    'ai_recommendation': {'run_id', 'claim_id', 'rule_id', 'request_id', 'model', 'prompt_version',
                          'used_fallback', 'source', 'output_hash', 'action_type', 'auto_correct_applied',
                          'escalated_to', 'confidence', 'confidence_kind'},
    'ai_failure': {'run_id', 'claim_id', 'rule_id', 'request_id', 'error', 'action_type'},
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
    if kind in ('ai_request', 'ai_recommendation', 'ai_failure'):
        if event['action_type'] in FORBIDDEN_AI_ACTIONS:
            raise ValueError('AI auto-correction is not permitted: AI actions must be human_escalation')
        if event['action_type'] not in AI_ACTION_TYPES:
            raise ValueError(f"Unknown AI action type: {event['action_type']!r}")
    if kind == 'ai_recommendation' and event['auto_correct_applied'] is not False:
        raise ValueError('auto_correct_applied must be false: the AI never changes a claim or result')


class AuditLog:
    """Append-only chain writer. Loads and fully verifies the existing log once
    at open; later appends only need the tail state."""

    def __init__(self, path):
        self.path = Path(path)
        self.anchor_path = self.path.with_name(self.path.name + '.head.json')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # If an anchor exists, check against it BEFORE anything is appended. Otherwise the
        # next write would re-anchor the truncated state and erase the evidence.
        if self.anchor_path.exists():
            self.head, self.count = verify_with_anchor(self.path, self.anchor_path)
        else:
            self.head, self.count = verify(self.path)

    def append_system_events(self, events):
        for e in events:
            _validate_system_event(e)
        if not events:
            return self.head, self.count
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
            f.flush()
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
    if anchor['count'] == 0:
        return head, count
    rows = [json.loads(l) for l in log_path.read_text(encoding='utf-8').splitlines() if l.strip()]
    if rows[anchor['count'] - 1]['hash'] != anchor['head']:
        raise ValueError('Log replaced: hash at anchored position differs from the anchor')
    return head, count


class AuditHooks:
    """review_package() lifecycle hooks that write the audit trail AHEAD of each action."""

    def __init__(self, log, source_format='normalized_json', ingestion_report=None):
        self.log = log
        self.source_format = source_format
        self.report = ingestion_report or {}

    def on_start(self, run_id, claim, input_hash, started_at):
        self.log.append_system_events([
            {'event_type': 'ingestion', 'claim_id': claim['claim_id'], 'source_format': self.source_format,
             'outcome': 'accepted', 'warnings': self.report.get('warnings', []),
             'not_carried_by_source': self.report.get('not_carried_by_fhir', [])},
            {'event_type': 'run_started', 'run_id': run_id, 'claim_id': claim['claim_id'],
             'input_hash': input_hash, 'started_at': started_at},
        ])

    def on_checks(self, run_id, claim, rule_results):
        self.log.append_system_events([{
            'event_type': 'rule_check', 'run_id': run_id, 'claim_id': claim['claim_id'],
            'rule_id': r['rule_id'], 'rule_version': r['rule_version'], 'status': r['status'],
            'severity': r['severity'], 'affected_line_ids': r['affected_line_ids'],
            'result_hash': digest(r), 'confidence': r['confidence'],
            'confidence_kind': r['confidence_kind'], 'method': r['method'],
        } for r in rule_results])

    def before_ai(self, request):
        self.log.append_system_events([{'event_type': 'ai_request', **request}])

    def after_ai(self, request, drafted, error):
        base = {'run_id': request['run_id'], 'claim_id': request['claim_id'], 'rule_id': request['rule_id'],
                'request_id': request['request_id'], 'action_type': request['action_type']}
        if drafted is None:
            self.log.append_system_events([{'event_type': 'ai_failure', **base, 'error': error}])
            return
        used_fallback = drafted['used_fallback']
        # The text came from a template if the fallback ran OR the primary provider is itself the template.
        from_template = used_fallback or request['model'] == 'deterministic-template'
        self.log.append_system_events([{
            'event_type': 'ai_recommendation', **base,
            'model': 'deterministic-template' if from_template else request['model'],
            'prompt_version': request['prompt_version'], 'used_fallback': used_fallback,
            'source': 'deterministic_template' if from_template else 'model',
            'error': drafted['error'], 'latency_ms': drafted['latency_ms'], 'usage': drafted['usage'],
            'output_hash': digest(drafted['output']), 'explanation': drafted['output']['explanation'],
            'auto_correct_applied': False, 'escalated_to': 'human_reviewer',
            # The explanation contract carries no score; never fabricate one.
            'confidence': None, 'confidence_kind': 'not_probabilistic',
        }])


def audited_review(log, claim, cfg, provider=None, fallback=None, untrusted_note=None,
                   source_format='normalized_json', ingestion_report=None, run_id=None):
    """Run review_package() with write-ahead auditing. Returns the same
    (rule_results, ai_explanations, run_trace)."""
    from claim_review import review_package
    hooks = AuditHooks(log, source_format, ingestion_report)
    rule_results, ai, trace = review_package(claim, cfg, provider=provider, fallback=fallback,
                                             untrusted_note=untrusted_note, hooks=hooks, run_id=run_id)
    claim_id, run_id = trace['claim_id'], trace['run_id']
    if rule_results is None:
        log.append_system_events([
            {'event_type': 'ingestion', 'claim_id': claim_id, 'source_format': source_format,
             'outcome': 'quarantined', 'error': trace.get('ingestion_error')},
            {'event_type': 'system_decision', 'run_id': run_id, 'claim_id': claim_id,
             'decision': 'quarantine_claim', 'reason': trace.get('ingestion_error', 'ingestion failed')},
        ])
        return rule_results, ai, trace
    needs_review = [r for r in rule_results if r['requires_human_review']]
    log.append_system_events([
        {'event_type': 'system_decision', 'run_id': run_id, 'claim_id': claim_id,
         'decision': 'route_to_human_review' if needs_review else 'no_findings_for_review',
         'reason': (f"{len(needs_review)} finding(s) require human review: "
                    + ', '.join(f"{r['rule_id']}={r['status']}" for r in needs_review)) if needs_review
                   else 'No FAIL or UNABLE_TO_ASSESS findings. This is not an approval.'},
        {'event_type': 'run_finished', 'run_id': run_id, 'claim_id': claim_id,
         'rule_pack_hash': trace['rule_pack_hash'], 'rule_versions': trace['rule_versions'],
         'tool_errors': trace['tool_errors'], 'finished_at': trace['finished_at']},
    ])
    return rule_results, ai, trace


def verify_ai_ordering(log_path):
    """Check, from the log alone, that every AI action was registered before it happened and
    classified. Raises ValueError listing violations; returns summary statistics.

    For every ai_request: the run had started and the rule's deterministic rule_check (with the
    same status) was already logged; the action type is human_escalation. For every outcome
    (ai_recommendation / ai_failure): a matching earlier ai_request exists, answered once, same
    run / claim / rule, recorded no earlier than the request, action type human_escalation and
    auto_correct_applied false. A run that finished with an unanswered request is a violation."""
    rows = [json.loads(l) for l in Path(log_path).read_text(encoding='utf-8').splitlines() if l.strip()]
    started, checks, finished = set(), {}, set()
    requests, answered = {}, set()
    problems = []
    stats = {'ai_requests': 0, 'ai_recommendations': 0, 'ai_failures': 0, 'unanswered_requests': 0,
             'action_types': {}, 'sources': {}}
    for row in rows:
        e, seq = row['event'], row['sequence']
        kind = e.get('event_type')
        if kind == 'run_started':
            started.add(e['run_id'])
        elif kind == 'run_finished':
            finished.add(e['run_id'])
        elif kind == 'rule_check':
            checks[(e['run_id'], e['rule_id'])] = e['status']
        elif kind == 'ai_request':
            stats['ai_requests'] += 1
            rid = e['request_id']
            if rid in requests:
                problems.append(f'seq {seq}: duplicate request_id {rid}')
            if e['run_id'] not in started:
                problems.append(f"seq {seq}: ai_request before run_started for run {e['run_id']}")
            logged = checks.get((e['run_id'], e['rule_id']))
            if logged is None:
                problems.append(f"seq {seq}: ai_request for {e['rule_id']} before its rule_check was logged")
            elif logged != e['deterministic_status']:
                problems.append(f"seq {seq}: ai_request status {e['deterministic_status']} != logged rule_check {logged}")
            if e['action_type'] not in AI_ACTION_TYPES:
                problems.append(f"seq {seq}: forbidden/unknown action_type {e['action_type']!r}")
            requests[rid] = (seq, row['recorded_at'], e)
        elif kind in ('ai_recommendation', 'ai_failure'):
            stats['ai_recommendations' if kind == 'ai_recommendation' else 'ai_failures'] += 1
            rid = e.get('request_id')
            req = requests.get(rid)
            if req is None:
                problems.append(f'seq {seq}: {kind} with no earlier ai_request ({rid})')
                continue
            if rid in answered:
                problems.append(f'seq {seq}: request {rid} answered twice')
            answered.add(rid)
            rq = req[2]
            if (e['run_id'], e['claim_id'], e['rule_id']) != (rq['run_id'], rq['claim_id'], rq['rule_id']):
                problems.append(f'seq {seq}: {kind} does not match its request')
            if row['recorded_at'] < req[1]:
                problems.append(f'seq {seq}: {kind} recorded before its request')
            if e['action_type'] not in AI_ACTION_TYPES:
                problems.append(f"seq {seq}: forbidden/unknown action_type {e['action_type']!r}")
            stats['action_types'][e['action_type']] = stats['action_types'].get(e['action_type'], 0) + 1
            if kind == 'ai_recommendation':
                if e['auto_correct_applied'] is not False:
                    problems.append(f'seq {seq}: auto_correct_applied is not false')
                stats['sources'][e['source']] = stats['sources'].get(e['source'], 0) + 1
    for rid, (seq, _, rq) in requests.items():
        if rid not in answered:
            if rq['run_id'] in finished:
                problems.append(f'seq {seq}: request {rid} was never answered although its run finished')
            else:
                stats['unanswered_requests'] += 1
    if problems:
        raise ValueError('AI audit ordering violations:\n  ' + '\n  '.join(problems[:20]))
    return stats


def events_for_quarantined_record(source_ref, source_format, error, claim_id='UNKNOWN'):
    """A record that never became a claim (bad JSON, unmappable bundle, failed
    transport contract). It is logged and routed to quarantine, never dropped."""
    return [
        {'event_type': 'ingestion', 'claim_id': claim_id, 'source_format': source_format,
         'outcome': 'quarantined', 'source_ref': source_ref, 'error': error},
        {'event_type': 'system_decision', 'run_id': None, 'claim_id': claim_id,
         'decision': 'quarantine_claim', 'reason': error},
    ]
