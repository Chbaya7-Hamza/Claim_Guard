import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


def write_jsonl(path, rows):
    path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')


class DeriveGoldStatusTests(unittest.TestCase):
    def test_any_fail_row_makes_the_claim_invalid(self):
        from score_clinicproj_comparison import derive_claim_status
        rows = [{'status': 'PASS'}, {'status': 'FAIL'}, {'status': 'PASS'}]
        self.assertEqual(derive_claim_status(rows), 'INVALID')

    def test_unable_to_assess_without_fail_is_review_required(self):
        from score_clinicproj_comparison import derive_claim_status
        rows = [{'status': 'PASS'}, {'status': 'UNABLE_TO_ASSESS'}]
        self.assertEqual(derive_claim_status(rows), 'REVIEW_REQUIRED')

    def test_all_pass_is_valid(self):
        from score_clinicproj_comparison import derive_claim_status
        rows = [{'status': 'PASS'}, {'status': 'NOT_APPLICABLE'}]
        self.assertEqual(derive_claim_status(rows), 'VALID')


class CorrectnessScoreTests(unittest.TestCase):
    def test_full_agreement_scores_100(self):
        from score_clinicproj_comparison import correctness_score
        gold = {'CG-1': 'INVALID', 'CG-2': 'VALID'}
        predicted = {'CG-1': 'INVALID', 'CG-2': 'VALID'}
        self.assertEqual(correctness_score(gold, predicted), 100.0)

    def test_half_agreement_scores_50(self):
        from score_clinicproj_comparison import correctness_score
        gold = {'CG-1': 'INVALID', 'CG-2': 'VALID'}
        predicted = {'CG-1': 'VALID', 'CG-2': 'VALID'}
        self.assertEqual(correctness_score(gold, predicted), 50.0)

    def test_incomplete_maps_to_review_required(self):
        from score_clinicproj_comparison import correctness_score
        gold = {'CG-1': 'REVIEW_REQUIRED'}
        predicted = {'CG-1': 'INCOMPLETE'}
        self.assertEqual(correctness_score(gold, predicted), 100.0)


class RapidnessScoreTests(unittest.TestCase):
    def test_faster_system_scores_100_slower_is_proportional(self):
        from score_clinicproj_comparison import rapidness_scores
        latencies = {'claimguard': [2.0, 4.0], 'clinicproj': [8.0, 8.0]}
        scores = rapidness_scores(latencies)
        self.assertEqual(scores['claimguard'], 100.0)
        self.assertEqual(scores['clinicproj'], 37.5)  # median 3.0 / median 8.0 * 100


class EfficiencyScoreTests(unittest.TestCase):
    def test_fewer_dependencies_scores_higher(self):
        from score_clinicproj_comparison import efficiency_score
        scores = efficiency_score({'claimguard': 3, 'clinicproj': 16})
        self.assertEqual(scores['clinicproj'], 0.0)   # has the max -- 1 - 16/16 = 0
        self.assertEqual(scores['claimguard'], 81.25)  # 100 * (1 - 3/16)

    def test_equal_counts_score_equally(self):
        from score_clinicproj_comparison import efficiency_score
        scores = efficiency_score({'claimguard': 5, 'clinicproj': 5})
        self.assertEqual(scores['claimguard'], scores['clinicproj'])


class CountRequirementsTests(unittest.TestCase):
    def test_counts_only_real_dependency_lines(self):
        from score_clinicproj_comparison import _count_requirements
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'requirements.txt'
            f.write_text("# a comment\nfoo==1.0\n\nbar==2.0\n  # indented comment\nbaz==3.0\n", encoding='utf-8')
            self.assertEqual(_count_requirements(f), 3)


class SecurityScoreTests(unittest.TestCase):
    def test_claimguard_is_always_100(self):
        from score_clinicproj_comparison import security_score
        scores = security_score({'dangerous_sinks': [], 'has_citation_grounding': False, 'injection_resistance': None})
        self.assertEqual(scores['claimguard'], 100.0)

    def test_clean_report_scores_100(self):
        from score_clinicproj_comparison import security_score
        report = {'dangerous_sinks': [], 'has_citation_grounding': True,
                   'injection_resistance': {'injected_claim_incorrectly_marked_valid': False, 'genuine_finding_suppressed': False}}
        self.assertEqual(security_score(report)['clinicproj'], 100.0)

    def test_dangerous_sink_and_no_grounding_each_deduct(self):
        from score_clinicproj_comparison import security_score
        report = {'dangerous_sinks': [{'file': 'agent.py', 'lineno': 1, 'line': 'eval(x)'}],
                   'has_citation_grounding': False, 'injection_resistance': None}
        self.assertEqual(security_score(report)['clinicproj'], 50.0)  # 100 - 25 - 25

    def test_full_injection_failure_deducts_more_than_partial_suppression(self):
        from score_clinicproj_comparison import security_score
        full_failure = {'dangerous_sinks': [], 'has_citation_grounding': True,
                         'injection_resistance': {'injected_claim_incorrectly_marked_valid': True, 'genuine_finding_suppressed': False}}
        partial = {'dangerous_sinks': [], 'has_citation_grounding': True,
                   'injection_resistance': {'injected_claim_incorrectly_marked_valid': False, 'genuine_finding_suppressed': True}}
        self.assertEqual(security_score(full_failure)['clinicproj'], 70.0)   # 100 - 30
        self.assertEqual(security_score(partial)['clinicproj'], 80.0)        # 100 - 20
        self.assertGreater(security_score(partial)['clinicproj'], security_score(full_failure)['clinicproj'])

    def test_deductions_stack_and_the_result_is_floored_at_zero(self):
        from score_clinicproj_comparison import security_score
        report = {'dangerous_sinks': [{'file': 'a.py', 'lineno': 1, 'line': 'eval(x)'}],
                   'has_citation_grounding': False,
                   'injection_resistance': {'injected_claim_incorrectly_marked_valid': True, 'genuine_finding_suppressed': False}}
        self.assertEqual(security_score(report)['clinicproj'], 20.0)  # 100 - 25 - 25 - 30 = 20
        self.assertGreaterEqual(security_score(report)['clinicproj'], 0.0)


class WeightedVerdictTests(unittest.TestCase):
    def test_overall_is_the_weighted_sum_and_names_a_winner(self):
        from score_clinicproj_comparison import weighted_verdict, WEIGHTS
        category_scores = {
            'correctness': {'claimguard': 100.0, 'clinicproj': 50.0},
            'security': {'claimguard': 100.0, 'clinicproj': 60.0},
            'deliverability': {'claimguard': 100.0, 'clinicproj': 20.0},
            'rapidness': {'claimguard': 100.0, 'clinicproj': 80.0},
            'efficiency': {'claimguard': 100.0, 'clinicproj': 40.0},
        }
        verdict = weighted_verdict(category_scores)
        expected_cg = sum(WEIGHTS[c] * category_scores[c]['claimguard'] for c in WEIGHTS) / 100
        self.assertAlmostEqual(verdict['overall']['claimguard'], expected_cg)
        self.assertEqual(verdict['overall']['winner'], 'claimguard')
        self.assertEqual(verdict['categories']['correctness']['winner'], 'claimguard')

    def test_a_split_verdict_is_reported_not_hidden(self):
        from score_clinicproj_comparison import weighted_verdict
        category_scores = {
            'correctness': {'claimguard': 100.0, 'clinicproj': 90.0},
            'security': {'claimguard': 100.0, 'clinicproj': 90.0},
            'deliverability': {'claimguard': 100.0, 'clinicproj': 90.0},
            'rapidness': {'claimguard': 60.0, 'clinicproj': 100.0},
            'efficiency': {'claimguard': 90.0, 'clinicproj': 90.0},
        }
        verdict = weighted_verdict(category_scores)
        self.assertEqual(verdict['categories']['rapidness']['winner'], 'clinicproj')
        self.assertEqual(verdict['overall']['winner'], 'claimguard')  # 92.5 vs 91.5 -- wins overall despite losing rapidness


if __name__ == '__main__':
    unittest.main()
