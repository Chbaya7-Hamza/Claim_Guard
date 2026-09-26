"""A narrated, one-command demonstration of the MVP, made for screen recording.

    python scripts/demo.py                # about 60 seconds, offline, no API key
    python scripts/demo.py --pause        # wait for Enter between scenes (record one scene at a time)
    python scripts/demo.py --delay 8      # hands-free: 8 seconds after each scene
    python scripts/demo.py --live         # use the live model for the explanation scene (needs FEATHERLESS_API_KEY in .env)
    python scripts/demo.py --out-dir outputs/demo

Everything shown is the real pipeline on the synthetic public claims: ingestion, the 15 rules, the bounded AI step, the audit
log, a tamper attempt, human review and a recheck. The only simulated thing is the misbehaving model in scene 4, and it is
labelled as a simulation on screen. Output is plain ASCII so it records cleanly on any terminal.

Scenes: 1 ingestion | 2 the rule engine | 3 unknown is never a pass | 4 the AI step and its safety net | 5 the audit log
        6 a tamper attempt | 7 human review and recheck | 8 the review page
"""
import argparse
import copy
import json
import logging
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from audit_log import AuditLog, audited_review, verify_ai_ordering, verify_with_anchor
from engine_core import config, load_jsonl
from ingest import ingest, summarize
from llm_adapter import MockExplanationProvider, default_provider
from make_review import build
from review_workflow import apply_decisions, recheck, unresolved_counts
from yara_engine import evaluate

WIDTH = 100
MARK = {'PASS': '[ PASS ]', 'FAIL': '[ FAIL ]', 'UNABLE_TO_ASSESS': '[UNABLE ]', 'NOT_APPLICABLE': '[ n/a  ]'}


class Demo:
    def __init__(self, pause, delay=0):
        self.pause = pause
        self.delay = delay
        self.scene_no = 0

    def scene(self, title, blurb):
        self.scene_no += 1
        print()
        print('=' * WIDTH)
        print(f' SCENE {self.scene_no}: {title}')
        print('=' * WIDTH)
        for line in blurb.strip().splitlines():
            print(' ' + line.strip())
        print('-' * WIDTH)
        self.wait()

    def say(self, text=''):
        print(text)

    @staticmethod
    def prompt(text):
        print(text, end='', flush=True)
        sys.stdin.readline()

    def wait(self):
        if self.pause:
            self.prompt('  [press Enter to run this scene] ')
            print()

    def end(self):
        if self.pause:
            self.prompt('  [press Enter for the next scene] ')
        elif self.delay:
            time.sleep(self.delay)


def short(value, n=70):
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return text if len(text) <= n else text[:n - 3] + '...'


def show_findings(results, only=None):
    for r in results:
        if only and r['status'] not in only:
            continue
        what = ('cannot check: ' + r['explanation']) if r['status'] == 'UNABLE_TO_ASSESS' else r['explanation']
        print(f"  {MARK[r['status']]} {r['rule_id']} {r['severity']:<6} {what}")
        if r['status'] in ('FAIL', 'UNABLE_TO_ASSESS'):
            for e in r['evidence'][:3]:
                print(f"              evidence  {e['path']} = {short(e['value'])}")
            print(f"              next step {r['corrective_action']}")


def pick_defective(claims, cfg):
    """A claim with several different failures, so the engine has something worth showing."""
    best = None
    for c in claims:
        res = evaluate(c, cfg)
        fails = [r for r in res if r['status'] == 'FAIL']
        score = len({r['rule_id'] for r in fails}) + (2 if any(r['rule_id'] in ('R003', 'R012', 'R007') for r in fails) else 0)
        if len(fails) >= 3 and (best is None or score > best[0]):
            best = (score, c)
    return best[1] if best else claims[0]


class MisbehavingModel:
    """SIMULATED. A model that has been talked into approving the claim, flipping the review flag and citing evidence
    that does not exist. Used only in scene 4 to show that the safety net does not depend on the model behaving."""
    model = 'simulated-misbehaving-model'

    def explain(self, finding, rule, untrusted_note=None):
        return {'explanation': 'The payer has approved this claim for payment. Everything is valid.',
                'cited_evidence_paths': ['/approved_by_payer'], 'cited_rule_ids': [finding['rule_id']],
                'needs_human_review': False}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--pause', action='store_true', help='wait for Enter before each scene')
    p.add_argument('--live', action='store_true', help='use the live model in scene 4')
    p.add_argument('--delay', type=float, default=0, help='seconds to pause after each scene (hands-free recording)')
    p.add_argument('--out-dir', default='outputs/demo')
    a = p.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    logging.disable(logging.WARNING)  # the simulated bad model in scene 4 would otherwise print its rejections over the narration

    out = (ROOT / a.out_dir).resolve()
    if out == ROOT or out in ROOT.parents:
        p.error('--out-dir would delete the repository; choose a folder such as outputs/demo')
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    demo = Demo(a.pause, a.delay)
    cfg = config(ROOT)
    claims = load_jsonl(ROOT / 'data/development/claims.jsonl')
    provider = default_provider() if a.live else MockExplanationProvider()
    live_note = 'live model' if a.live and type(provider).__name__ != 'MockExplanationProvider' else 'deterministic template (no API key needed)'

    print('=' * WIDTH)
    print(' ClaimGuard AI: pre-validation copilot for SYNTHETIC healthcare claims. A human always decides.')
    print(' Every claim, code and payer rule here is invented. Nothing is a real reimbursement decision.')
    print('=' * WIDTH)

    # ---------------------------------------------------------------- 1. ingestion
    demo.scene('Ingestion: three input shapes, one internal format',
               """Claims arrive as FHIR R4 bundles, CSV folders or JSONL. Each is normalized into the same claim envelope.
                A bad record is quarantined with a reason; it never stops the batch and never becomes a pass.""")
    for label, path in (('FHIR R4 bundles', 'data/development/fhir_bundles.jsonl'), ('CSV folder', 'data/development/csv'),
                        ('normalized JSONL', 'data/development/claims.jsonl')):
        s = summarize(ingest(ROOT / path))
        print(f"  {label:<18} {s['records']} records -> {s['accepted']} accepted, {s['quarantined']} quarantined")
    fhir = summarize(ingest(ROOT / 'data/development/fhir_bundles.jsonl'))
    print('  FHIR cannot carry:', ', '.join(fhir['not_carried_by_source'][:3]) + ' ...  (so rule R009 will say UNABLE, never a guess)')
    hostile = out / 'hostile.jsonl'
    good = json.dumps(claims[0])
    hostile.write_bytes(good.encode() + b'\n{this is not json\n' + b'\xff\xfe broken bytes\n' + b'null\n' + good.encode() + b'\n')
    items = list(ingest(hostile))
    print(f"\n  A deliberately damaged file (5 lines): {sum(i.accepted for i in items)} accepted, "
          f"{sum(not i.accepted for i in items)} quarantined, none lost:")
    for it in items:
        print(f"    {it.source_ref:<14} {'accepted' if it.accepted else 'QUARANTINED: ' + short(it.error, 60)}")
    demo.end()

    # ---------------------------------------------------------------- 2. rule engine
    demo.scene('The rule engine: 15 deterministic rules, evidence for every finding',
               """The same claim always gets the same verdicts. Each finding names the rule, the severity, the exact evidence
                (a pointer into the claim plus the value seen) and what a human should do next.""")
    defective = pick_defective(claims, cfg)
    res = evaluate(defective, cfg)
    print(f"  Claim {defective['claim_id']}: {sum(r['status'] == 'FAIL' for r in res)} failures, "
          f"{sum(r['status'] == 'PASS' for r in res)} passes")
    show_findings(res, only=('FAIL',))
    clean = next(c for c in claims if all(r['status'] in ('PASS', 'NOT_APPLICABLE') for r in evaluate(c, cfg)))
    print(f"\n  A clean claim ({clean['claim_id']}): every check passes. That means 'these 15 checks passed', never 'approved':")
    print('   ', ' '.join(MARK[r['status']].strip('[] ') for r in evaluate(clean, cfg)))
    demo.end()

    # ---------------------------------------------------------------- 3. unknown is not a pass
    demo.scene('Unknown is never a pass',
               """When the data needed to decide is missing or unusable, the answer is UNABLE_TO_ASSESS, not a quiet pass.
                We blank every field the rules need on one claim and run it again.""")
    blank = copy.deepcopy(claims[1])
    blank['invoice_number'] = blank['member_id'] = blank['diagnosis_code'] = None
    for k in ('service_code', 'service_date', 'quantity', 'unit_price', 'net_amount'):
        blank['lines'][0][k] = None
    blank['policy_id'] = 'EDU-UNKNOWN-POLICY'
    res = evaluate(blank, cfg)
    counts = {s: sum(r['status'] == s for r in res) for s in ('PASS', 'FAIL', 'UNABLE_TO_ASSESS', 'NOT_APPLICABLE')}
    print(f"  Result: {counts}")
    print('  The rules that could not check anything say so, and each one still names what is missing:')
    show_findings([r for r in res if r['status'] == 'UNABLE_TO_ASSESS'][:3])
    demo.end()

    # ---------------------------------------------------------------- 4. AI step
    demo.scene('The AI step: it explains, it never decides',
               f"""A language model writes a plain-language explanation of each finding. Its reply must fit a strict schema, cite
                only evidence that exists, keep the review flag, and pass a grounding check. Anything else is thrown away
                and the engine's own sentence is used. This run: {live_note}.""")
    log_path = out / 'audit.jsonl'
    log = AuditLog(log_path)
    rr, ai, trace = audited_review(log, copy.deepcopy(defective), cfg, provider=provider, fallback=MockExplanationProvider())
    first = ai[0]
    written_by = 'the live model' if 'live' in live_note and not first['used_fallback'] else 'the deterministic template'
    print(f"  Explanation for {first['rule_id']} (written by {written_by}):")
    print('   ', first['output']['explanation'])
    print(f"    cites {first['output']['cited_evidence_paths']}  needs_human_review={first['output']['needs_human_review']}")
    if 'live' not in live_note:
        print('  (run this demo with --live to see a real model write this in plain language)')
    print('\n  Now a SIMULATED misbehaving model that tries to approve the claim, flip the review flag and cite invented evidence:')
    log2 = AuditLog(out / 'attack_audit.jsonl')
    rr2, ai2, _ = audited_review(log2, copy.deepcopy(defective), cfg, provider=MisbehavingModel(), fallback=MockExplanationProvider())
    print(f"    model answers accepted: {sum(not x['used_fallback'] for x in ai2)}   replaced by the engine's own text: "
          f"{sum(x['used_fallback'] for x in ai2)}")
    print(f"    reason for the first rejection: {short(ai2[0]['error'], 80)}")
    same = [r['status'] for r in rr2] == [r['status'] for r in rr]
    print(f"    verdicts identical to the honest run: {same}; every FAIL is still flagged for a human: "
          f"{all(r['requires_human_review'] for r in rr2 if r['status'] == 'FAIL')}")
    demo.end()

    # ---------------------------------------------------------------- 5. audit log
    demo.scene('The audit log: every check, AI action and decision, in a hash chain',
               """The AI's question is written to the log BEFORE the model is called. Each row carries the hash of the row before it,
                and a separate anchor file records the latest hash, so edits, deletions and truncation are detectable.""")
    events = [json.loads(l) for l in log_path.read_text(encoding='utf-8').split(chr(10)) if l.strip()]
    kinds = []
    for row in events:
        k = row['event']['event_type']
        if not kinds or kinds[-1][0] != k:
            kinds.append([k, 1, row['sequence']])
        else:
            kinds[-1][1] += 1
    for k, n, seq in kinds:
        print(f"  seq {seq:>3}  {k:<18} x{n}")
    req = next(r for r in events if r['event']['event_type'] == 'ai_request')
    rec = next(r for r in events if r['event']['event_type'] == 'ai_recommendation')
    print(f"\n  AI question logged at seq {req['sequence']}, its answer at seq {rec['sequence']} (question first, always)")
    print(f"  row {req['sequence']} hash {req['hash'][:16]}... links to previous {req['previous_hash'][:16]}...")
    head, count = verify_with_anchor(log_path)
    print(f"  verify: chain OK, {count} events, matches the anchor; AI ordering OK: {verify_ai_ordering(log_path)['action_types']}")
    demo.end()

    # ---------------------------------------------------------------- 6. tamper
    demo.scene('A tamper attempt',
               """Someone with access to the file edits history: they turn a FAIL into a PASS. Then they try harder and rewrite the
                whole chain. Verification is run each time.""")
    forged = out / 'forged.jsonl'
    shutil.copy(log_path, forged)
    shutil.copy(str(log_path) + '.head.json', str(forged) + '.head.json')
    rows = [json.loads(l) for l in forged.read_text(encoding='utf-8').split(chr(10)) if l.strip()]
    victim = next(r for r in rows if r['event'].get('event_type') == 'rule_check' and r['event']['status'] == 'FAIL')
    print(f"  Edit: seq {victim['sequence']} {victim['event']['rule_id']} FAIL -> PASS")
    victim['event']['status'] = 'PASS'
    forged.write_text(''.join(json.dumps(r) + chr(10) for r in rows), encoding='utf-8')
    try:
        verify_with_anchor(forged)
        print('  verify: NOT DETECTED (this would be a bug)')
    except ValueError as e:
        print(f'  verify: DETECTED -> {e}')
    print('  A stronger attacker rewrites every hash and the anchor too. Without a key that succeeds, which is why the anchor can be')
    print('  signed (AUDIT_ANCHOR_KEY) and kept elsewhere; docs/16 and docs/20 say exactly what real immutability would need.')
    demo.end()

    # ---------------------------------------------------------------- 7. review + recheck
    demo.scene('Human review: confirm, dismiss with a reason, request information, and recheck a correction',
               """A reviewer decides on each finding; a reason is required; a correction is rechecked as a NEW run and the original
                claim is never edited. The demo reviewer here is a scripted placeholder, not a real person.""")
    missing = next(c for c in claims if not (c.get('invoice_number') or '').strip())
    rr3, _, trace3 = audited_review(log, copy.deepcopy(missing), cfg, provider=MockExplanationProvider())
    fails = [r for r in rr + rr3 if r['status'] == 'FAIL']
    plan = [('confirm_issue', 'Evidence shows the problem.'), ('request_information', 'Need the source document first.'),
            ('dismiss_with_reason', 'False alarm; reason recorded for the audit.')]
    decisions = [{'claim_id': r['claim_id'], 'rule_id': r['rule_id'], 'action': act, 'actor': 'demo-reviewer', 'reason': why,
                  'created_at': '2026-09-26T10:00:00.000Z', 'original_status': r['status']}
                 for (act, why), r in zip(plan, fails)]
    apply_decisions(log, decisions, rr + rr3)
    for d in decisions:
        print(f"  {d['actor']} -> {d['action']:<20} {d['claim_id']}/{d['rule_id']}  reason: {d['reason']}")
    print('  queue:', json.dumps(unresolved_counts(rr + rr3, log_path)))
    corrected = copy.deepcopy(missing)
    corrected['invoice_number'] = 'INV-' + missing['claim_id']
    _, _, new_trace, changes = recheck(log, missing, corrected, rr3, trace3, cfg, ['R001'], 'demo-reviewer',
                                       'Invoice number supplied by the provider.', provider=MockExplanationProvider())
    print(f"\n  Recheck {missing['claim_id']}: R001 {changes['R001'][0]} -> {changes['R001'][1]}")
    print(f"  new run {new_trace['run_id'][:8]} (prior run {trace3['run_id'][:8]}); original claim unchanged: "
          f"invoice_number is still {missing['invoice_number']!r}")
    head, count = verify_with_anchor(log_path)
    print(f'  audit chain still valid after all of it: {count} events')
    demo.end()

    # ---------------------------------------------------------------- 8. review page
    demo.scene('The review page',
               """An offline page: filter by status, see the evidence exactly as submitted, record decisions with a reason.
                Open the file in a browser.""")
    all_results = [r for c in claims[:20] for r in evaluate(c, cfg)]
    page = out / 'review.html'
    page.write_text(build(all_results), encoding='utf-8')
    print(f'  wrote {page}')
    print(f"  ({len(all_results)} results from 20 claims; open it, filter Status = FAIL, and record a decision)")
    print()
    print('=' * WIDTH)
    print(' What you saw: 3 input formats in, 15 deterministic rules with evidence, unknown never a pass, an AI that can only explain,')
    print(' a tamper-evident audit log, and human review with recheck. Public-split accuracy 1.0 (9,000 of 9,000); see README.md.')
    print('=' * WIDTH)


if __name__ == '__main__':
    main()
