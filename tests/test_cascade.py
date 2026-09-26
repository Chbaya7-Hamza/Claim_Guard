"""A cascade of model tiers: fluent when the first tier behaves, reliable when it does not, the template as the floor.

Every tier is untrusted: it gets a private copy of the finding, its reply passes the same schema and grounding checks as a
single provider's, and the audit log names the tier that actually wrote the text.
"""
import copy
import json
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))
from audit_log import AuditLog, audited_review, verify_ai_ordering, verify_with_anchor
from claim_review import draft_and_validate_explanation
from engine_core import config
from llm_adapter import CascadeError, CascadeExplanationProvider, MockExplanationProvider
from test_stress_boundaries import CLEAN
from yara_engine import evaluate

FINDING = {'claim_id': 'CG-1', 'rule_id': 'R012', 'status': 'FAIL', 'requires_human_review': True,
           'explanation': 'Claim total does not equal the sum of line amounts.',
           'evidence': [{'path': '/total_amount', 'value': 1.0}]}
RULE = {'rule_id': 'R012', 'title': 'Claim total equals line amounts'}


def answer(text='The claim total 1.0 differs from the sum of the line amounts. Verify the total against the source record.'):
    return {'explanation': text, 'cited_evidence_paths': ['/total_amount'], 'cited_rule_ids': ['R012'],
            'needs_human_review': True}


class Tier:
    def __init__(self, model, reply=None, error=None):
        self.model, self.reply, self.error, self.calls = model, reply, error, 0
        self.last_usage = {'total_tokens': 100}
        self.last_attempts = 1

    def explain(self, finding, rule, untrusted_note=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.reply() if callable(self.reply) else self.reply


GARBLED = answer('The total is 1.0 ' + chr(0x6570) + chr(0x4e0b) + chr(0x7684) + ' which differs from the lines.')


class CascadeBehaviour(unittest.TestCase):
    def test_the_first_tier_answers_when_it_behaves_and_the_second_is_not_called(self):
        first, second = Tier('mistral', answer()), Tier('qwen7', answer())
        c = CascadeExplanationProvider([first, second])
        out = c.explain(copy.deepcopy(FINDING), RULE)
        self.assertEqual((c.answered_by, c.tier_errors, second.calls), ('mistral', [], 0))
        self.assertEqual(out['needs_human_review'], True)
        self.assertEqual(c.last_usage, {'total_tokens': 100})

    def test_a_garbled_first_tier_hands_over_to_the_second(self):
        c = CascadeExplanationProvider([Tier('mistral', GARBLED), Tier('qwen7', answer())])
        c.explain(copy.deepcopy(FINDING), RULE)
        self.assertEqual(c.answered_by, 'qwen7')
        self.assertEqual([e['model'] for e in c.tier_errors], ['mistral'])
        self.assertIn('garbled', c.tier_errors[0]['error'])

    def test_a_tier_that_raises_hands_over_too(self):
        c = CascadeExplanationProvider([Tier('mistral', error=TimeoutError('slow')), Tier('qwen7', answer())])
        c.explain(copy.deepcopy(FINDING), RULE)
        self.assertEqual(c.answered_by, 'qwen7')
        self.assertIn('TimeoutError', c.tier_errors[0]['error'])

    def test_no_tier_is_trusted_including_the_last_live_one(self):
        wrong_rule = dict(answer(), cited_rule_ids=['R999'])
        flipped = dict(answer(), needs_human_review=False)
        for bad in (GARBLED, wrong_rule, flipped, None, 'text', {}):
            c = CascadeExplanationProvider([Tier('mistral', bad), Tier('qwen7', bad)])
            with self.assertRaises(CascadeError):
                c.explain(copy.deepcopy(FINDING), RULE)
            self.assertEqual(len(c.tier_errors), 2)
            self.assertIsNone(c.answered_by)

    def test_a_tier_cannot_edit_the_finding_the_next_tier_sees(self):
        seen = []

        def evil():
            return answer()

        class Mutating(Tier):
            def explain(self, finding, rule, untrusted_note=None):
                finding['status'] = 'PASS'
                finding['evidence'].clear()
                return super().explain(finding, rule, untrusted_note)

        class Spy(Tier):
            def explain(self, finding, rule, untrusted_note=None):
                seen.append(copy.deepcopy(finding))
                return super().explain(finding, rule, untrusted_note)

        original = copy.deepcopy(FINDING)
        c = CascadeExplanationProvider([Mutating('a', GARBLED), Spy('b', answer())])
        c.explain(FINDING, RULE)
        self.assertEqual(seen[0], original)
        self.assertEqual(FINDING, original)

    def test_concurrent_calls_each_report_their_own_tier(self):
        import time

        class ByClaim(Tier):
            """Fails for odd claim numbers and dawdles, so calls from different threads overlap."""

            def explain(self, finding, rule, untrusted_note=None):
                time.sleep(0.02)
                if int(finding['claim_id'].split('-')[1]) % 2:
                    raise RuntimeError('odd claim')
                return answer()

        c = CascadeExplanationProvider([ByClaim('mistral'), Tier('qwen7', answer())])

        def run(n):
            finding = dict(copy.deepcopy(FINDING), claim_id=f'CG-{n}')
            c.explain(finding, RULE)
            time.sleep(0.02)
            return n, c.answered_by, [e['model'] for e in c.tier_errors]

        with ThreadPoolExecutor(max_workers=8) as pool:
            got = list(pool.map(run, range(40)))
        for n, tier, errors in got:
            self.assertEqual((tier, errors), (('qwen7', ['mistral']) if n % 2 else ('mistral', [])), n)

    def test_it_needs_at_least_one_tier(self):
        with self.assertRaises(ValueError):
            CascadeExplanationProvider([])


class CascadeInThePipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config(ROOT)

    def run_claim(self, provider):
        claim = copy.deepcopy(CLEAN)
        claim['total_amount'] = 1.0  # R012 FAIL
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.jsonl'
            rr, ai, _ = audited_review(AuditLog(path), claim, self.cfg, provider=provider, fallback=MockExplanationProvider())
            verify_with_anchor(path)
            verify_ai_ordering(path)
            events = [json.loads(l)['event'] for l in path.read_text(encoding='utf-8').split(chr(10)) if l.strip()]
        return claim, rr, ai, [e for e in events if e['event_type'] == 'ai_recommendation']

    def test_the_audit_log_names_the_tier_that_wrote_the_text(self):
        claim, rr, ai, recs = self.run_claim(CascadeExplanationProvider([Tier('mistral', GARBLED), Tier('qwen7', answer())]))
        self.assertEqual(rr, evaluate(claim, self.cfg))
        self.assertEqual([r['model'] for r in recs], ['qwen7'])
        self.assertEqual(recs[0]['source'], 'model')
        self.assertFalse(recs[0]['used_fallback'])
        self.assertEqual(recs[0]['tier_errors'][0]['model'], 'mistral')
        self.assertEqual(ai[0]['answered_by'], 'qwen7')

    def test_a_first_tier_answer_is_logged_as_the_first_tier_with_no_tier_errors(self):
        _, _, _, recs = self.run_claim(CascadeExplanationProvider([Tier('mistral', answer()), Tier('qwen7', answer())]))
        self.assertEqual((recs[0]['model'], recs[0]['tier_errors']), ('mistral', []))

    def test_when_every_tier_fails_the_template_is_used_and_logged_as_the_template(self):
        claim, rr, ai, recs = self.run_claim(CascadeExplanationProvider([Tier('mistral', GARBLED), Tier('qwen7', GARBLED)]))
        self.assertEqual(rr, evaluate(claim, self.cfg))  # the finding is untouched
        self.assertEqual(recs[0]['model'], 'deterministic-template')
        self.assertEqual(recs[0]['source'], 'deterministic_template')
        self.assertTrue(recs[0]['used_fallback'])
        self.assertIn('mistral', recs[0]['error'])
        self.assertIn('qwen7', recs[0]['error'])

    def test_a_single_provider_is_logged_exactly_as_before(self):
        _, _, _, recs = self.run_claim(MockExplanationProvider())
        self.assertEqual(recs[0]['model'], 'deterministic-template')
        self.assertEqual(recs[0]['tier_errors'], [])

    def test_draft_and_validate_reports_the_tier(self):
        c = CascadeExplanationProvider([Tier('mistral', error=RuntimeError('boom')), Tier('qwen7', answer())])
        out = draft_and_validate_explanation(copy.deepcopy(FINDING), RULE, c, MockExplanationProvider())
        self.assertEqual((out['answered_by'], out['used_fallback']), ('qwen7', False))


class DefaultProviderConfiguration(unittest.TestCase):
    def setUp(self):
        import os
        self.os = os
        self.saved = {k: os.environ.get(k) for k in ('FEATHERLESS_API_KEY', 'FEATHERLESS_FALLBACK_MODEL', 'FEATHERLESS_MODEL')}
        os.environ['FEATHERLESS_API_KEY'] = 'not-a-real-key'
        os.environ.pop('FEATHERLESS_FALLBACK_MODEL', None)
        os.environ.pop('FEATHERLESS_MODEL', None)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                self.os.environ.pop(k, None)
            else:
                self.os.environ[k] = v

    def test_by_default_one_model_and_no_cascade(self):
        from llm_adapter import default_provider, FeatherlessExplanationProvider
        p = default_provider()
        self.assertIsInstance(p, FeatherlessExplanationProvider)
        self.assertEqual(p.model, 'mistralai/Mistral-Nemo-Instruct-2407')
        self.assertEqual((p.temperature, p.top_p), (0, 1))

    def test_a_fallback_model_in_the_environment_turns_on_the_cascade(self):
        from llm_adapter import default_provider
        self.os.environ['FEATHERLESS_FALLBACK_MODEL'] = 'Qwen/Qwen2.5-7B-Instruct'
        p = default_provider()
        self.assertIsInstance(p, CascadeExplanationProvider)
        self.assertEqual([t.model for t in p.tiers], ['mistralai/Mistral-Nemo-Instruct-2407', 'Qwen/Qwen2.5-7B-Instruct'])

    def test_the_round_one_model_is_still_one_setting_away(self):
        from llm_adapter import default_provider
        self.os.environ['FEATHERLESS_MODEL'] = 'Qwen/Qwen2.5-14B-Instruct'
        self.assertEqual(default_provider().model, 'Qwen/Qwen2.5-14B-Instruct')


if __name__ == '__main__':
    unittest.main()
