import unittest, sys, json, copy
from pathlib import Path
from unittest.mock import MagicMock
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config
from llm_adapter import MockExplanationProvider
from claim_review import (
    IngestionError, validate_input, resolve_policy, run_checks, retrieve_evidence,
    draft_and_validate_explanation, review_package,
)


class OrchestratorStepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config(ROOT)
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_validate_input_passes_through_a_clean_claim(self):
        self.assertIs(validate_input(self.c), self.c)

    def test_validate_input_raises_ingestion_error_on_malformed_claim(self):
        del self.c['coverage']
        with self.assertRaises(IngestionError):
            validate_input(self.c)

    def test_resolve_policy_returns_matching_policy(self):
        policy = resolve_policy(self.c, self.cfg)
        self.assertEqual(policy['policy_id'], self.c['policy_id'])

    def test_resolve_policy_returns_none_for_unknown_policy_never_invents_one(self):
        self.c['policy_id'] = 'EDU-NOPE'
        self.assertIsNone(resolve_policy(self.c, self.cfg))

    def test_run_checks_returns_all_15_rules(self):
        results = run_checks(self.c, self.cfg)
        self.assertEqual({r['rule_id'] for r in results}, {f'R{i:03}' for i in range(1, 16)})

    def test_retrieve_evidence_returns_a_value_already_on_the_finding(self):
        finding = {'evidence': [{'path': '/invoice_number', 'value': 'INV-1'}]}
        self.assertEqual(retrieve_evidence(finding, '/invoice_number'), 'INV-1')

    def test_retrieve_evidence_refuses_a_path_not_on_the_finding(self):
        finding = {'evidence': [{'path': '/invoice_number', 'value': 'INV-1'}]}
        with self.assertRaises(KeyError):
            retrieve_evidence(finding, '/member_id')


class DraftAndValidateExplanationTests(unittest.TestCase):
    FINDING_FAIL = {
        'claim_id': 'CG-TEST', 'rule_id': 'R001', 'status': 'FAIL',
        'evidence': [{'path': '/invoice_number', 'value': None}],
        'explanation': 'Required information is missing.', 'requires_human_review': True,
    }
    FINDING_PASS = {**FINDING_FAIL, 'status': 'PASS', 'requires_human_review': False}
    RULE = {'rule_id': 'R001', 'title': 'x'}

    def test_skips_pass_findings(self):
        provider = MagicMock()
        out = draft_and_validate_explanation(self.FINDING_PASS, self.RULE, provider, MockExplanationProvider())
        self.assertIsNone(out)
        provider.explain.assert_not_called()

    def test_drafts_for_fail_findings(self):
        provider = MagicMock()
        provider.explain.return_value = MockExplanationProvider().explain(self.FINDING_FAIL, self.RULE)
        out = draft_and_validate_explanation(self.FINDING_FAIL, self.RULE, provider, MockExplanationProvider())
        self.assertEqual(out['rule_id'], 'R001')
        self.assertFalse(out['used_fallback'])

    def test_falls_back_and_marks_it_on_provider_failure(self):
        provider = MagicMock()
        provider.explain.side_effect = TimeoutError('simulated')
        out = draft_and_validate_explanation(self.FINDING_FAIL, self.RULE, provider, MockExplanationProvider())
        self.assertTrue(out['used_fallback'])
        self.assertIn('TimeoutError', out['error'])


class ReviewPackageTests(unittest.TestCase):
    """Uses a stub provider (no live API) -- these test the orchestration
    logic, not NVIDIA connectivity, which test_llm_adapter.py already covers
    with the real provider class mocked at the client level."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = config(ROOT)
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_ingestion_error_returns_no_results_but_a_run_trace(self):
        del self.c['coverage']
        rule_results, ai_explanations, trace = review_package(
            self.c, self.cfg, provider=MockExplanationProvider(), fallback=MockExplanationProvider())
        self.assertIsNone(rule_results)
        self.assertIsNone(ai_explanations)
        self.assertIn('ingestion_error', trace)
        self.assertEqual(trace['claim_id'], self.c['claim_id'])

    def test_clean_claim_produces_15_results_and_no_explanations(self):
        # The worked-cases claim is clean -- every rule PASSes, so nothing
        # needs an AI explanation.
        rule_results, ai_explanations, trace = review_package(
            self.c, self.cfg, provider=MockExplanationProvider(), fallback=MockExplanationProvider())
        self.assertEqual(len(rule_results), 15)
        self.assertEqual(ai_explanations, [])
        self.assertNotIn('ingestion_error', trace)
        self.assertTrue(trace['policy_resolved'])

    def test_ai_explanations_never_appear_inside_rule_results(self):
        self.c['invoice_number'] = None  # forces R001 to FAIL
        rule_results, ai_explanations, trace = review_package(
            self.c, self.cfg, provider=MockExplanationProvider(), fallback=MockExplanationProvider())
        r001 = next(r for r in rule_results if r['rule_id'] == 'R001')
        self.assertEqual(r001['status'], 'FAIL')
        self.assertNotIn('ai_explanation', r001)  # rule_results schema is untouched
        self.assertTrue(any(e['rule_id'] == 'R001' for e in ai_explanations))

    def test_run_trace_has_required_fields_separate_from_results(self):
        rule_results, ai_explanations, trace = review_package(
            self.c, self.cfg, provider=MockExplanationProvider(), fallback=MockExplanationProvider())
        for key in ('run_id', 'claim_id', 'input_hash', 'rule_pack_hash', 'model',
                    'prompt_version', 'tool_errors', 'started_at', 'finished_at'):
            self.assertIn(key, trace)
        self.assertEqual(len(trace['input_hash']), 64)  # sha256 hex digest

    def test_unavailable_policy_never_invents_a_fallback_policy(self):
        self.c['policy_id'] = 'EDU-NOPE'
        rule_results, ai_explanations, trace = review_package(
            self.c, self.cfg, provider=MockExplanationProvider(), fallback=MockExplanationProvider())
        self.assertFalse(trace['policy_resolved'])
        # Policy-dependent rules must degrade to UNABLE_TO_ASSESS, not silently PASS.
        for rid in ('R005', 'R008', 'R013', 'R014', 'R015'):
            r = next(r for r in rule_results if r['rule_id'] == rid)
            self.assertEqual(r['status'], 'UNABLE_TO_ASSESS')


if __name__ == '__main__':
    unittest.main()
