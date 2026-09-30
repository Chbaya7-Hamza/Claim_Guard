"""Tests for the tool-capable-model re-run of the clinicProj comparison: lenient JSON extraction is recorded beside the
strict result, the hallucination metric, and the rebalanced weights."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


class LenientParseTests(unittest.TestCase):
    def test_fenced_json_is_recorded_as_lenient_but_strict_status_stays_none(self):
        from run_clinicproj_comparison import parse_clinicproj_reply
        r = parse_clinicproj_reply('Here you go:\n```json\n{"overall_status": "INVALID"}\n```')
        self.assertIsNone(r['status'])
        self.assertEqual(r['lenient_status'], 'INVALID')
        self.assertTrue(r['wrapped_json'])

    def test_prose_without_json_has_no_lenient_status(self):
        from run_clinicproj_comparison import parse_clinicproj_reply
        r = parse_clinicproj_reply('It seems there was an error in the calculation.')
        self.assertIsNone(r['lenient_status'])
        self.assertFalse(r['wrapped_json'])


class HallucinationTests(unittest.TestCase):
    CLAIM = {'claim_id': 'C1', 'currency': 'USD', 'total_amount': 100, 'lines': [{'line_id': 'L1', 'net_amount': 100.0}]}
    GOLD = {'C1': [{'rule_id': 'R015', 'status': 'FAIL'}, {'rule_id': 'R001', 'status': 'PASS'}]}

    def _score(self, findings):
        import json
        from score_clinicproj_comparison import hallucination_score
        row = {'claim_id': 'C1', 'raw_output': json.dumps({'findings': findings})}
        return hallucination_score('clinicproj', [row], {'C1': self.CLAIM}, self.GOLD)

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
        from score_clinicproj_comparison import hallucination_score
        s = hallucination_score('clinicproj', [{'claim_id': 'C1', 'raw_output': 'prose only'}], {'C1': self.CLAIM}, self.GOLD)
        self.assertEqual(s['score'], 0.0)


class WeightsTests(unittest.TestCase):
    def test_both_weight_sets_sum_to_100_and_hallucination_switches_them(self):
        from score_clinicproj_comparison import WEIGHTS, WEIGHTS_WITH_HALLUCINATION, weighted_verdict
        self.assertEqual(sum(WEIGHTS.values()), 100)
        self.assertEqual(sum(WEIGHTS_WITH_HALLUCINATION.values()), 100)
        scores = {c: {'claimguard': 100.0, 'clinicproj': 0.0} for c in WEIGHTS_WITH_HALLUCINATION}
        self.assertEqual(weighted_verdict(scores)['overall']['claimguard'], 100.0)


if __name__ == '__main__':
    unittest.main()
