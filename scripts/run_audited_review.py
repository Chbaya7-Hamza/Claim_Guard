"""End-to-end auditable sample run (offline, deterministic, no API key needed).

    ingest -> bounded review (15 rules + explanations) -> audit log
           -> reviewer decisions (validated) -> corrected-claim recheck -> verify chain

Writes to outputs/audit_demo/ (results.jsonl, review_decisions.jsonl,
audit.jsonl, audit.jsonl.head.json). Explanations use the deterministic
template provider unless --live is passed (NVIDIA-backed model, needs .env).

The reviewer decisions and the correction in this script are DEMONSTRATION
data under the actor 'demo-reviewer'; they show the workflow and the audit
trail, not real human judgement.
"""
import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from audit_log import AuditLog, events_for_quarantined_record, events_for_run, verify_with_anchor
from claim_review import review_package
from engine_core import config
from ingest import ingest
from llm_adapter import MockExplanationProvider, default_provider
from review_workflow import apply_decisions, load_decisions, recheck, unresolved_counts

REVIEWABLE = ('FAIL', 'UNABLE_TO_ASSESS')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--input', default='data/development/claims.jsonl',
                   help='normalized JSONL, FHIR Bundle JSONL, or a CSV folder (auto-detected)')
    p.add_argument('--limit', type=int, default=12)
    p.add_argument('--out-dir', default='outputs/audit_demo')
    p.add_argument('--live', action='store_true', help='use the NVIDIA-backed explanation provider')
    a = p.parse_args()

    out = ROOT / a.out_dir
    out.mkdir(parents=True, exist_ok=True)
    for f in ('audit.jsonl', 'audit.jsonl.head.json', 'results.jsonl', 'review_decisions.jsonl'):
        (out / f).unlink(missing_ok=True)

    cfg = config(ROOT)
    log = AuditLog(out / 'audit.jsonl')
    ingested = list(ingest(ROOT / a.input))
    for it in ingested:
        if not it.accepted:
            log.append_system_events(events_for_quarantined_record(it.source_ref, it.source_format, it.error))
    claims = [it.claim for it in ingested if it.accepted]
    reports = {it.claim['claim_id']: (it.source_format, it.report) for it in ingested if it.accepted}
    provider = default_provider() if a.live else MockExplanationProvider()

    # Pick the sample: first `limit` claims, plus one known invoice_number failure so the recheck has something to fix.
    sample = claims[:a.limit]
    demo_claim = next((c for c in claims if not (c.get('invoice_number') or '').strip()), None)
    if demo_claim and all(c['claim_id'] != demo_claim['claim_id'] for c in sample):
        sample.append(demo_claim)

    runs = {}
    all_results = []
    for claim in sample:
        rr, ai, trace = review_package(copy.deepcopy(claim), cfg, provider=provider)
        fmt, report = reports[claim['claim_id']]
        log.append_system_events(events_for_run(claim, rr, ai, trace, source_format=fmt, ingestion_report=report))
        runs[claim['claim_id']] = (claim, rr, trace)
        all_results.extend(rr or [])
    with (out / 'results.jsonl').open('w', encoding='utf-8') as f:
        for r in all_results:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'Reviewed {len(sample)} claims -> {len(all_results)} rule results; audit chain has {log.count} events.')

    # Three demonstration decisions, one per kind that is not a recheck.
    reviewable = [r for r in all_results if r['status'] in REVIEWABLE]
    actions = ['confirm_issue', 'request_information', 'dismiss_with_reason']
    reasons = {
        'confirm_issue': 'DEMO: reviewer agrees the cited evidence shows the problem.',
        'request_information': 'DEMO: need the source document before deciding.',
        'dismiss_with_reason': 'DEMO: reviewer believes this is a false alarm; reason recorded for audit.',
    }
    decisions = [{'claim_id': r['claim_id'], 'rule_id': r['rule_id'], 'action': act, 'actor': 'demo-reviewer',
                  'reason': reasons[act], 'created_at': '2026-09-23T12:00:00.000Z',
                  'original_status': r['status']}
                 for act, r in zip(actions, reviewable[:3])]
    with (out / 'review_decisions.jsonl').open('w', encoding='utf-8') as f:
        for d in decisions:
            f.write(json.dumps(d) + '\n')
    apply_decisions(log, load_decisions(out / 'review_decisions.jsonl'), all_results)
    print('Queue after decisions:', json.dumps(unresolved_counts(all_results, out / 'audit.jsonl')))

    # Recheck: the reviewer supplies the missing invoice number; the original claim/run stay untouched.
    if demo_claim:
        claim, rr, trace = runs[demo_claim['claim_id']]
        corrected = copy.deepcopy(claim)
        corrected['invoice_number'] = f"INV-{claim['claim_id']}"  # DEMO value, mirrors the pack's own invoice pattern
        _, _, new_trace, changes = recheck(
            log, claim, corrected, rr, trace, cfg, ['R001'], 'demo-reviewer',
            'DEMO: invoice number supplied by the provider.', provider=provider)
        print(f"Recheck {claim['claim_id']}: R001 {changes['R001'][0]} -> {changes['R001'][1]} "
              f"(new run {new_trace['run_id'][:8]}, prior run {trace['run_id'][:8]})")

    head, count = verify_with_anchor(out / 'audit.jsonl')
    print(f'Audit chain valid: {count} events; head {head}')


if __name__ == '__main__':
    main()
