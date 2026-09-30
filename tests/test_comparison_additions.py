"""Tests for the tool-capable-model re-run of the Architecture B comparison: lenient JSON extraction is recorded beside the
strict result, the hallucination metric, and the rebalanced weights."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


class LenientParseTests(unittest.TestCase):
    def test_fenced_json_is_recorded_as_lenient_but_strict_status_stays_none(self):
        from run_architecture_comparison import parse_architecture_b_reply
        r = parse_architecture_b_reply('Here you go:\n```json\n{"overall_status": "INVALID"}\n```')
        self.assertIsNone(r['status'])
        self.assertEqual(r['lenient_status'], 'INVALID')
        self.assertTrue(r['wrapped_json'])

    def test_prose_without_json_has_no_lenient_status(self):
        from run_architecture_comparison import parse_architecture_b_reply
        r = parse_architecture_b_reply('It seems there was an error in the calculation.')
        self.assertIsNone(r['lenient_status'])
        self.assertFalse(r['wrapped_json'])


class ExtractJsonObjectTests(unittest.TestCase):
    def test_prose_with_braces_before_the_json_does_not_break_extraction(self):
        from run_architecture_comparison import extract_json_object
        obj = extract_json_object('Note {see below}: ```json\n{"overall_status": "invalid", "findings": []}\n``` done {x}')
        self.assertEqual(obj['overall_status'], 'invalid')

    def test_no_object_returns_none(self):
        from run_architecture_comparison import extract_json_object
        self.assertIsNone(extract_json_object('no json here {not json}'))

    def test_lenient_status_is_upper_cased(self):
        from run_architecture_comparison import parse_architecture_b_reply
        self.assertEqual(parse_architecture_b_reply('text {"overall_status": "invalid"}')['lenient_status'], 'INVALID')


class DotenvTests(unittest.TestCase):
    def _load(self, module, text):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / '.env').write_text(text, encoding='utf-8')
            old_root = module.ROOT
            module.ROOT = Path(d)
            for k in ('TEST_QUOTED', 'TEST_SINGLE', 'TEST_EXPORT', 'TEST_PLAIN'):
                os.environ.pop(k, None)
            try:
                module._load_dotenv()
            finally:
                module.ROOT = old_root
            return {k: os.environ.pop(k, None) for k in ('TEST_QUOTED', 'TEST_SINGLE', 'TEST_EXPORT', 'TEST_PLAIN')}

    TEXT = 'TEST_QUOTED="abc def"\nTEST_SINGLE=\'xyz\'\nexport TEST_EXPORT=exp\nTEST_PLAIN=plain  \n# comment=1\n'
    EXPECTED = {'TEST_QUOTED': 'abc def', 'TEST_SINGLE': 'xyz', 'TEST_EXPORT': 'exp', 'TEST_PLAIN': 'plain'}

    def test_harness_loader_strips_quotes_and_export(self):
        import run_architecture_comparison as m
        self.assertEqual(self._load(m, self.TEXT), self.EXPECTED)

    def test_llm_adapter_loader_strips_quotes_and_export(self):
        sys.path.insert(0, str(ROOT / 'src'))
        import llm_adapter as m
        self.assertEqual(self._load(m, self.TEXT), self.EXPECTED)


class HallucinationTests(unittest.TestCase):
    CLAIM = {'claim_id': 'C1', 'currency': 'USD', 'total_amount': 100, 'lines': [{'line_id': 'L1', 'net_amount': 100.0}]}
    GOLD = {'C1': [{'rule_id': 'R015', 'status': 'FAIL'}, {'rule_id': 'R001', 'status': 'PASS'}]}

    def _score(self, findings):
        import json
        from score_architecture_comparison import hallucination_score
        row = {'claim_id': 'C1', 'raw_output': json.dumps({'findings': findings})}
        return hallucination_score('architecture_b', [row], {'C1': self.CLAIM}, self.GOLD)

    def test_a_correct_grounded_finding_scores_100(self):
        s = self._score([{'rule_id': 'R015', 'status': 'FAIL', 'evidence': [{'value': 'USD'}]}])
        self.assertEqual(s['score'], 100.0)

    def test_a_fail_the_key_says_passed_is_fabricated(self):
        s = self._score([{'rule_id': 'R001', 'status': 'FAIL', 'evidence': []}])
        self.assertEqual(s['fabricated_findings'], 1)
        self.assertLess(s['score'], 100.0)

    def test_an_invented_rule_id_is_fabricated(self):
        s = self._score([{'rule_id': 'R999', 'status': 'FAIL', 'evidence': []}])
        self.assertEqual(s['fabricated_findings'], 1)

    def test_evidence_not_in_the_claim_is_ungrounded_but_a_reformatted_number_is_not(self):
        s = self._score([{'rule_id': 'R015', 'status': 'FAIL',
                          'evidence': [{'value': '100.0'}, {'value': 'EUR'}]}])
        self.assertEqual((s['evidence_items'], s['ungrounded_evidence']), (2, 1))

    def test_no_parseable_answer_scores_zero_not_a_free_hundred(self):
        from score_architecture_comparison import hallucination_score
        s = hallucination_score('architecture_b', [{'claim_id': 'C1', 'raw_output': 'prose only'}], {'C1': self.CLAIM}, self.GOLD)
        self.assertEqual(s['score'], 0.0)


class WeightsTests(unittest.TestCase):
    def test_both_weight_sets_sum_to_100_and_hallucination_switches_them(self):
        from score_architecture_comparison import WEIGHTS, WEIGHTS_WITH_HALLUCINATION, weighted_verdict
        self.assertEqual(sum(WEIGHTS.values()), 100)
        self.assertEqual(sum(WEIGHTS_WITH_HALLUCINATION.values()), 100)
        scores = {c: {'architecture_a': 100.0, 'architecture_b': 0.0} for c in WEIGHTS_WITH_HALLUCINATION}
        self.assertEqual(weighted_verdict(scores)['overall']['architecture_a'], 100.0)


if __name__ == '__main__':
    unittest.main()
