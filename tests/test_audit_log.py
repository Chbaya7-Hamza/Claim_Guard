import unittest, sys, json, copy, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config
from audit import verify
from audit_log import AuditLog, verify_with_anchor, events_for_run, events_for_quarantined_record
from claim_review import review_package
from llm_adapter import MockExplanationProvider


def run_events(claim, cfg):
    rr, ai, trace = review_package(claim, cfg, provider=MockExplanationProvider())
    return events_for_run(claim, rr, ai, trace), rr, ai, trace


class AuditLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config(ROOT)
        cls.clean = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'audit.jsonl'

    def tearDown(self):
        self.tmp.cleanup()

    def failing_claim(self):
        c = copy.deepcopy(self.clean)
        c['invoice_number'] = None
        return c

    def test_run_records_every_check_ai_recommendation_and_decision(self):
        events, rr, ai, _ = run_events(self.failing_claim(), self.cfg)
        kinds = [e['event_type'] for e in events]
        self.assertEqual(kinds.count('rule_check'), 15)
        self.assertEqual(kinds.count('ai_recommendation'), len(ai))
        self.assertGreaterEqual(kinds.count('ai_recommendation'), 1)
        decision = next(e for e in events if e['event_type'] == 'system_decision')
        self.assertEqual(decision['decision'], 'route_to_human_review')
        self.assertIn('R001=FAIL', decision['reason'])
        self.assertEqual(kinds[0], 'ingestion')
        self.assertEqual(kinds[-1], 'run_finished')

    def test_clean_claim_is_never_recorded_as_approved(self):
        events, *_ = run_events(self.clean, self.cfg)
        decision = next(e for e in events if e['event_type'] == 'system_decision')
        self.assertEqual(decision['decision'], 'no_findings_for_review')
        self.assertIn('not an approval', decision['reason'])

    def test_rule_check_confidence_is_null_not_invented(self):
        events, *_ = run_events(self.failing_claim(), self.cfg)
        for e in events:
            if e['event_type'] in ('rule_check', 'ai_recommendation'):
                self.assertIsNone(e['confidence'])
                self.assertEqual(e['confidence_kind'], 'not_probabilistic')

    def test_rule_check_hash_matches_the_stored_result(self):
        from audit import digest
        events, rr, *_ = run_events(self.failing_claim(), self.cfg)
        by_rule = {r['rule_id']: r for r in rr}
        for e in events:
            if e['event_type'] == 'rule_check':
                self.assertEqual(e['result_hash'], digest(by_rule[e['rule_id']]))

    def test_written_log_verifies_with_the_supplied_verifier(self):
        log = AuditLog(self.path)
        events, *_ = run_events(self.failing_claim(), self.cfg)
        log.append_system_events(events)
        head, n = verify(self.path)
        self.assertEqual((head, n), (log.head, log.count))
        self.assertEqual(verify_with_anchor(self.path), (head, n))

    def test_reopening_continues_the_same_chain(self):
        events, *_ = run_events(self.clean, self.cfg)
        AuditLog(self.path).append_system_events(events)
        log2 = AuditLog(self.path)
        log2.append_system_events(events)
        self.assertEqual(verify(self.path)[1], 2 * len(events))

    def test_editing_an_event_is_detected(self):
        log = AuditLog(self.path)
        log.append_system_events(run_events(self.failing_claim(), self.cfg)[0])
        lines = self.path.read_text().splitlines()
        idx = next(i for i, l in enumerate(lines)
                   if json.loads(l)['event'].get('rule_id') == 'R001' and json.loads(l)['event']['event_type'] == 'rule_check')
        row = json.loads(lines[idx])
        self.assertEqual(row['event']['status'], 'FAIL')
        row['event']['status'] = 'PASS'  # rewrite history but leave the stored hash alone
        lines[idx] = json.dumps(row, ensure_ascii=False)
        self.path.write_text('\n'.join(lines) + '\n')
        with self.assertRaises((ValueError, json.JSONDecodeError)):
            verify(self.path)

    def test_truncation_is_detected_only_via_the_anchor(self):
        log = AuditLog(self.path)
        log.append_system_events(run_events(self.failing_claim(), self.cfg)[0])
        lines = self.path.read_text().splitlines()
        self.path.write_text('\n'.join(lines[:-3]) + '\n')
        verify(self.path)  # a bare chain cannot notice a clean truncation
        with self.assertRaisesRegex(ValueError, 'truncated'):
            verify_with_anchor(self.path)

    def test_whole_log_replacement_is_detected_by_the_anchor(self):
        log = AuditLog(self.path)
        log.append_system_events(run_events(self.failing_claim(), self.cfg)[0])
        anchor = self.path.with_name('audit.jsonl.head.json').read_text()
        other = Path(self.tmp.name) / 'other.jsonl'
        other_log = AuditLog(other)
        forged = run_events(self.clean, self.cfg)[0]
        other_log.append_system_events(forged * 2)  # longer, internally valid, different history
        self.path.write_bytes(other.read_bytes())
        self.path.with_name('audit.jsonl.head.json').write_text(anchor)
        with self.assertRaisesRegex(ValueError, 'replaced'):
            verify_with_anchor(self.path)

    def test_system_may_not_record_an_approval(self):
        log = AuditLog(self.path)
        bad = {'event_type': 'system_decision', 'run_id': 'r', 'claim_id': 'c',
               'decision': 'approve_claim', 'reason': 'x'}
        with self.assertRaises(ValueError):
            log.append_system_events([bad])
        self.assertEqual(log.count, 0)

    def test_fabricated_confidence_on_deterministic_event_is_rejected(self):
        log = AuditLog(self.path)
        events, *_ = run_events(self.failing_claim(), self.cfg)
        rc = next(e for e in events if e['event_type'] == 'rule_check')
        rc['confidence'] = 0.99
        with self.assertRaises(ValueError):
            log.append_system_events([rc])

    def test_unknown_event_type_is_rejected(self):
        with self.assertRaises(ValueError):
            AuditLog(self.path).append_system_events([{'event_type': 'note', 'x': 1}])

    def test_human_decisions_share_the_chain_and_stay_strict(self):
        log = AuditLog(self.path)
        log.append_system_events(run_events(self.failing_claim(), self.cfg)[0])
        before = log.count
        log.append_review_decisions([dict(claim_id='CG-X', rule_id='R001', action='request_information',
                                          actor='tester', reason='Need source invoice')])
        self.assertEqual(log.count, before + 1)
        self.assertEqual(verify_with_anchor(self.path)[1], before + 1)
        with self.assertRaises(ValueError):
            log.append_review_decisions([dict(claim_id='CG-X', rule_id='R001', action='dismiss_with_reason',
                                              actor='tester', reason='  ')])
        self.assertEqual(verify(self.path)[1], before + 1)

    def test_quarantined_claim_is_recorded_not_dropped(self):
        rr, ai, trace = review_package({'claim_id': 'CG-BAD'}, self.cfg, provider=MockExplanationProvider())
        events = events_for_run({'claim_id': 'CG-BAD'}, rr, ai, trace)
        self.assertEqual([e['event_type'] for e in events], ['ingestion', 'system_decision'])
        self.assertEqual(events[0]['outcome'], 'quarantined')
        AuditLog(self.path).append_system_events(events)

    def test_record_that_never_became_a_claim_is_logged_and_quarantined(self):
        events = events_for_quarantined_record('claims.jsonl:4', 'normalized_json', 'Invalid JSON: x')
        AuditLog(self.path).append_system_events(events)
        rows = [json.loads(l)['event'] for l in self.path.read_text().splitlines()]
        self.assertEqual((rows[0]['outcome'], rows[0]['source_ref']), ('quarantined', 'claims.jsonl:4'))
        self.assertEqual(rows[1]['decision'], 'quarantine_claim')

    def test_ingestion_event_carries_source_warnings_and_uncarried_fields(self):
        rr, ai, trace = review_package(copy.deepcopy(self.clean), self.cfg, provider=MockExplanationProvider())
        report = {'warnings': ['unresolved_reference: x'], 'not_carried_by_fhir': ['notes']}
        events = events_for_run(self.clean, rr, ai, trace, source_format='fhir_bundle', ingestion_report=report)
        self.assertEqual(events[0]['source_format'], 'fhir_bundle')
        self.assertEqual(events[0]['warnings'], ['unresolved_reference: x'])
        self.assertEqual(events[0]['not_carried_by_source'], ['notes'])


if __name__ == '__main__':
    unittest.main()
