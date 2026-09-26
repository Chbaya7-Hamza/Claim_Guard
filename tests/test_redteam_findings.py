"""Findings from the red-team run: replayed claims, and defects that none of the 15 rules cover.

Replays: a claim_id submitted again outside the recheck flow is logged as a duplicate_submission and routed to a human,
whether or not the content changed. Advisories (src/advisory.py): a diagnosis code outside the catalogue and a payer that
differs from the policy's are recorded and routed to a human, but are never rule results and never change a score.
"""
import copy
import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))
from advisory import advisory_checks
from audit_log import AuditLog, audited_review, verify_ai_ordering, verify_with_anchor
from engine_core import config, load_jsonl
from llm_adapter import MockExplanationProvider
from review_workflow import recheck
from test_stress_boundaries import CLEAN
from yara_engine import evaluate


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config(ROOT)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'audit.jsonl'
        self.log = AuditLog(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def submit(self, claim, log=None):
        return audited_review(log or self.log, copy.deepcopy(claim), self.cfg, provider=MockExplanationProvider())

    def events(self):
        return [json.loads(l)['event'] for l in self.path.read_text(encoding='utf-8').split(chr(10)) if l.strip()]

    def of(self, kind, claim_id=None):
        return [e for e in self.events() if e.get('event_type') == kind and (claim_id is None or e['claim_id'] == claim_id)]


class ReplayedClaims(Base):
    def test_a_first_submission_is_not_a_duplicate(self):
        self.submit(CLEAN)
        self.assertEqual(self.of('duplicate_submission'), [])
        self.assertEqual(self.of('system_decision')[0]['decision'], 'no_findings_for_review')

    def test_the_same_claim_again_is_logged_and_routed_to_a_human_even_when_clean(self):
        self.submit(CLEAN)
        self.submit(CLEAN)
        dup = self.of('duplicate_submission')
        self.assertEqual(len(dup), 1)
        self.assertTrue(dup[0]['same_input'])
        self.assertEqual(len(dup[0]['prior_run_ids']), 1)
        second = self.of('system_decision')[1]
        self.assertEqual(second['decision'], 'route_to_human_review')
        self.assertIn('duplicate submission', second['reason'])
        self.assertIn('identical content', second['reason'])

    def test_a_resubmission_with_changed_content_is_called_out_as_changed(self):
        self.submit(CLEAN)
        changed = copy.deepcopy(CLEAN)
        changed['total_amount'] = 1.0
        self.submit(changed)
        self.assertFalse(self.of('duplicate_submission')[0]['same_input'])
        self.assertIn('CHANGED content', self.of('system_decision')[1]['reason'])

    def test_three_submissions_list_every_earlier_run(self):
        for _ in range(3):
            self.submit(CLEAN)
        dups = self.of('duplicate_submission')
        self.assertEqual([len(d['prior_run_ids']) for d in dups], [1, 2])

    def test_a_different_claim_id_is_not_a_duplicate(self):
        self.submit(CLEAN)
        other = copy.deepcopy(CLEAN)
        other['claim_id'] = 'CG-OTHER'
        self.submit(other)
        self.assertEqual(self.of('duplicate_submission'), [])

    def test_a_reopened_log_still_knows_earlier_submissions(self):
        self.submit(CLEAN)
        self.submit(CLEAN, log=AuditLog(self.path))
        self.assertEqual(len(self.of('duplicate_submission')), 1)

    def test_simultaneous_submissions_of_one_claim_all_see_the_others(self):
        logs = [AuditLog(self.path) for _ in range(6)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda lg: self.submit(CLEAN, log=lg), logs))
        self.assertEqual(len(self.of('duplicate_submission')), 5)
        self.assertEqual(len(self.of('run_started')), 6)
        verify_with_anchor(self.path)

    def test_a_reviewer_requested_recheck_is_not_reported_as_a_duplicate(self):
        broken = copy.deepcopy(CLEAN)
        broken['total_amount'] = 1.0
        results, _, trace = self.submit(broken)
        fixed = copy.deepcopy(CLEAN)
        recheck(self.log, broken, fixed, results, trace, self.cfg, ['R012'], 'reviewer-1',
                'Total corrected against the source', provider=MockExplanationProvider(),
                fallback=MockExplanationProvider())
        self.assertEqual(self.of('duplicate_submission'), [])
        self.assertEqual(len(self.of('run_started')), 2)
        verify_with_anchor(self.path)
        verify_ai_ordering(self.path)


class AdvisoryChecks(Base):
    def test_a_clean_claim_has_no_advisories(self):
        self.assertEqual(advisory_checks(CLEAN, self.cfg), [])
        self.submit(CLEAN)
        self.assertEqual(self.of('advisory_check'), [])

    def test_an_unknown_diagnosis_code_is_recorded_and_routed_to_a_human(self):
        c = copy.deepcopy(CLEAN)
        c['diagnosis_code'] = 'DX-FAKE-999'
        rr, _, trace = self.submit(c)
        self.assertEqual([a['check_id'] for a in trace['advisories']], ['ADV-DIAGNOSIS-NOT-IN-CATALOGUE'])
        self.assertEqual([e['check_id'] for e in self.of('advisory_check')], ['ADV-DIAGNOSIS-NOT-IN-CATALOGUE'])
        decision = self.of('system_decision')[0]
        self.assertEqual(decision['decision'], 'route_to_human_review')
        self.assertIn('advisory checks outside the 15 rules', decision['reason'])

    def test_a_payer_that_differs_from_the_policy_is_recorded(self):
        c = copy.deepcopy(CLEAN)
        c['payer_id'] = 'OTHER-PAYER'
        self.assertEqual([a['check_id'] for a in advisory_checks(c, self.cfg)], ['ADV-PAYER-POLICY-MISMATCH'])

    def test_an_unknown_policy_gives_no_payer_advisory_because_there_is_nothing_to_compare(self):
        c = copy.deepcopy(CLEAN)
        c['policy_id'] = 'EDU-GHOST'
        c['payer_id'] = 'OTHER-PAYER'
        self.assertEqual(advisory_checks(c, self.cfg), [])

    def test_advisories_never_touch_the_scored_rule_results(self):
        c = copy.deepcopy(CLEAN)
        c['diagnosis_code'] = 'DX-FAKE-999'
        c['payer_id'] = 'OTHER-PAYER'
        rr, _, _ = self.submit(c)
        self.assertEqual(rr, evaluate(c, self.cfg))
        self.assertEqual({r['rule_id'] for r in rr}, {f'R{i:03d}' for i in range(1, 16)})
        self.assertTrue(all(r['status'] == 'PASS' for r in rr))  # still "15 checks passed": the advisory is separate

    def test_no_public_claim_triggers_an_advisory_so_no_existing_workflow_changes(self):
        for split in ('development', 'validation', 'stress'):
            for c in load_jsonl(ROOT / f'data/{split}/claims.jsonl'):
                self.assertEqual(advisory_checks(c, self.cfg), [], c['claim_id'])


if __name__ == '__main__':
    unittest.main()
