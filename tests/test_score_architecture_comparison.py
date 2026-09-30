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
        from score_architecture_comparison import derive_claim_status
        rows = [{'status': 'PASS'}, {'status': 'FAIL'}, {'status': 'PASS'}]
        self.assertEqual(derive_claim_status(rows), 'INVALID')

    def test_unable_to_assess_without_fail_is_review_required(self):
        from score_architecture_comparison import derive_claim_status
        rows = [{'status': 'PASS'}, {'status': 'UNABLE_TO_ASSESS'}]
        self.assertEqual(derive_claim_status(rows), 'REVIEW_REQUIRED')

    def test_all_pass_is_valid(self):
        from score_architecture_comparison import derive_claim_status
        rows = [{'status': 'PASS'}, {'status': 'NOT_APPLICABLE'}]
        self.assertEqual(derive_claim_status(rows), 'VALID')


class CorrectnessScoreTests(unittest.TestCase):
    def test_full_agreement_scores_100(self):
        from score_architecture_comparison import correctness_score
        gold = {'CG-1': 'INVALID', 'CG-2': 'VALID'}
        predicted = {'CG-1': 'INVALID', 'CG-2': 'VALID'}
        self.assertEqual(correctness_score(gold, predicted), 100.0)

    def test_half_agreement_scores_50(self):
        from score_architecture_comparison import correctness_score
        gold = {'CG-1': 'INVALID', 'CG-2': 'VALID'}
        predicted = {'CG-1': 'VALID', 'CG-2': 'VALID'}
        self.assertEqual(correctness_score(gold, predicted), 50.0)

    def test_incomplete_maps_to_review_required(self):
        from score_architecture_comparison import correctness_score
        gold = {'CG-1': 'REVIEW_REQUIRED'}
        predicted = {'CG-1': 'INCOMPLETE'}
        self.assertEqual(correctness_score(gold, predicted), 100.0)


class RapidnessScoreTests(unittest.TestCase):
    def test_faster_system_scores_100_slower_is_proportional(self):
        from score_architecture_comparison import rapidness_scores
        latencies = {'architecture_a': [2.0, 4.0], 'architecture_b': [8.0, 8.0]}
        scores = rapidness_scores(latencies)
        self.assertEqual(scores['architecture_a'], 100.0)
        self.assertEqual(scores['architecture_b'], 37.5)  # median 3.0 / median 8.0 * 100

    def test_a_system_with_no_successful_latencies_scores_zero_not_crashes(self):
        # A system whose every claim errored out (caller filters those rows
        # out before building this dict -- see main()) has nothing to time.
        # That must score 0, not raise, and must still appear in the result
        # so weighted_verdict() doesn't KeyError looking it up.
        from score_architecture_comparison import rapidness_scores
        scores = rapidness_scores({'architecture_a': [2.0], 'architecture_b': []})
        self.assertEqual(scores, {'architecture_a': 100.0, 'architecture_b': 0.0})

    def test_every_system_with_no_successful_latencies_scores_zero_not_crashes(self):
        from score_architecture_comparison import rapidness_scores
        scores = rapidness_scores({'architecture_a': [], 'architecture_b': []})
        self.assertEqual(scores, {'architecture_a': 0.0, 'architecture_b': 0.0})


class EfficiencyScoreTests(unittest.TestCase):
    def test_fewer_dependencies_scores_higher(self):
        # Normalized the same way as rapidness (ratio to the best, not "1 -
        # ratio to the worst"): the old formula always scored the heavier
        # system exactly 0 regardless of how close it actually was.
        from score_architecture_comparison import efficiency_score
        scores = efficiency_score({'architecture_a': 3, 'architecture_b': 16})
        self.assertEqual(scores['architecture_a'], 100.0)   # has the fewest -- 3/3
        self.assertEqual(scores['architecture_b'], 18.75)   # 100 * 3/16

    def test_equal_counts_score_equally_and_at_the_top(self):
        from score_architecture_comparison import efficiency_score
        scores = efficiency_score({'architecture_a': 5, 'architecture_b': 5})
        self.assertEqual(scores['architecture_a'], scores['architecture_b'])
        self.assertEqual(scores['architecture_a'], 100.0)  # a tie is not "worst", unlike the old formula


class CountRequirementsTests(unittest.TestCase):
    def test_counts_only_real_dependency_lines(self):
        from score_architecture_comparison import _count_requirements
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'requirements.txt'
            f.write_text("# a comment\nfoo==1.0\n\nbar==2.0\n  # indented comment\nbaz==3.0\n", encoding='utf-8')
            self.assertEqual(_count_requirements(f), 3)


class SecurityScoreTests(unittest.TestCase):
    """security_score(security_report) reads security_report['architecture_a'] and
    ['architecture_b'] as PEER sub-reports and scores both from real scan data --
    Architecture A's is measured the same way, not hardcoded. Its sub-report sets
    injection_probe_applicable=False (Architecture A's rule-engine-plus-explanation
    architecture has no free-text conversational surface to probe the way
    Architecture B's agent does; its injection resistance is covered by its own
    existing test suite instead -- see docs/24), so Architecture A is never
    penalized for a probe dimension that doesn't apply to it."""

    def test_a_clean_system_scores_100(self):
        from score_architecture_comparison import security_score
        report = {
            'architecture_b': {'dangerous_sinks': [], 'has_citation_grounding': True,
                            'injection_resistance': {'injected_claim_incorrectly_marked_valid': False,
                                                      'genuine_finding_suppressed': False}},
            'architecture_a': {'dangerous_sinks': [], 'has_citation_grounding': True,
                           'injection_probe_applicable': False},
        }
        scores = security_score(report)
        self.assertEqual(scores['architecture_b'], 100.0)
        self.assertEqual(scores['architecture_a'], 100.0)

    def test_architecture_a_is_measured_not_hardcoded(self):
        # A dangerous sink or missing grounding guard in Architecture A's own
        # code must lower its score exactly like it would for Architecture B --
        # this is what "measured, not assumed" means.
        from score_architecture_comparison import security_score
        report = {
            'architecture_b': {'dangerous_sinks': [], 'has_citation_grounding': True, 'injection_resistance': None},
            'architecture_a': {'dangerous_sinks': [{'file': 'x.py', 'lineno': 1, 'line': 'eval(x)'}],
                           'has_citation_grounding': False, 'injection_probe_applicable': False},
        }
        self.assertEqual(security_score(report)['architecture_a'], 50.0)  # 100 - 25 - 25, same formula as architecture_b

    def test_injection_probe_not_applicable_skips_that_deduction_entirely(self):
        from score_architecture_comparison import security_score
        report = {
            'architecture_b': {'dangerous_sinks': [], 'has_citation_grounding': True, 'injection_resistance': None},
            'architecture_a': {'dangerous_sinks': [], 'has_citation_grounding': True, 'injection_probe_applicable': False},
        }
        # architecture_a has no injection_resistance key at all, and the probe doesn't
        # apply to it -- must NOT fall into the "not verified" -15 tier.
        self.assertEqual(security_score(report)['architecture_a'], 100.0)

    def test_dangerous_sink_and_no_grounding_each_deduct(self):
        # injection_resistance=None here means the probe was never run
        # (--live not passed) -- that's not evidence of resistance either,
        # so it deducts the same -15 as a probe that ran and errored.
        from score_architecture_comparison import security_score
        report = {'architecture_b': {'dangerous_sinks': [{'file': 'agent.py', 'lineno': 1, 'line': 'eval(x)'}],
                                  'has_citation_grounding': False, 'injection_resistance': None},
                   'architecture_a': {'dangerous_sinks': [], 'has_citation_grounding': True, 'injection_probe_applicable': False}}
        self.assertEqual(security_score(report)['architecture_b'], 35.0)  # 100 - 25 - 25 - 15

    def test_an_unparseable_probe_reply_is_not_a_free_pass(self):
        # The reply wasn't JSON at all -- resisted is unknown, not True.
        from score_architecture_comparison import security_score
        report = {'architecture_b': {'dangerous_sinks': [], 'has_citation_grounding': True,
                                  'injection_resistance': {'parseable': False, 'injected_claim_incorrectly_marked_valid': None,
                                                            'genuine_finding_suppressed': None}},
                   'architecture_a': {'dangerous_sinks': [], 'has_citation_grounding': True, 'injection_probe_applicable': False}}
        self.assertEqual(security_score(report)['architecture_b'], 85.0)  # 100 - 15, same tier as a probe error

    def test_no_probe_at_all_deducts_the_same_as_a_probe_error(self):
        from score_architecture_comparison import security_score
        architecture_a = {'dangerous_sinks': [], 'has_citation_grounding': True, 'injection_probe_applicable': False}
        never_run = {'architecture_b': {'dangerous_sinks': [], 'has_citation_grounding': True, 'injection_resistance': None},
                     'architecture_a': architecture_a}
        errored = {'architecture_b': {'dangerous_sinks': [], 'has_citation_grounding': True,
                                   'injection_resistance': {'error': 'boom'}},
                   'architecture_a': architecture_a}
        self.assertEqual(security_score(never_run)['architecture_b'], security_score(errored)['architecture_b'])

    def test_full_injection_failure_deducts_more_than_partial_suppression(self):
        from score_architecture_comparison import security_score
        architecture_a = {'dangerous_sinks': [], 'has_citation_grounding': True, 'injection_probe_applicable': False}
        full_failure = {'architecture_b': {'dangerous_sinks': [], 'has_citation_grounding': True,
                                        'injection_resistance': {'injected_claim_incorrectly_marked_valid': True,
                                                                  'genuine_finding_suppressed': False}},
                        'architecture_a': architecture_a}
        partial = {'architecture_b': {'dangerous_sinks': [], 'has_citation_grounding': True,
                                   'injection_resistance': {'injected_claim_incorrectly_marked_valid': False,
                                                             'genuine_finding_suppressed': True}},
                   'architecture_a': architecture_a}
        self.assertEqual(security_score(full_failure)['architecture_b'], 70.0)   # 100 - 30
        self.assertEqual(security_score(partial)['architecture_b'], 80.0)        # 100 - 20
        self.assertGreater(security_score(partial)['architecture_b'], security_score(full_failure)['architecture_b'])

    def test_deductions_stack_and_the_result_is_floored_at_zero(self):
        from score_architecture_comparison import security_score
        report = {'architecture_b': {'dangerous_sinks': [{'file': 'a.py', 'lineno': 1, 'line': 'eval(x)'}],
                                  'has_citation_grounding': False,
                                  'injection_resistance': {'injected_claim_incorrectly_marked_valid': True,
                                                            'genuine_finding_suppressed': False}},
                   'architecture_a': {'dangerous_sinks': [], 'has_citation_grounding': True, 'injection_probe_applicable': False}}
        self.assertEqual(security_score(report)['architecture_b'], 20.0)  # 100 - 25 - 25 - 30 = 20
        self.assertGreaterEqual(security_score(report)['architecture_b'], 0.0)

    def test_a_probe_that_errored_is_not_a_free_pass(self):
        # run_injection_probe() can itself raise (e.g. the model can't run the
        # agent's tool-calling architecture at all) -- security_scan_architecture_b.py
        # then records {'error': ...} instead of a real result. That must NOT
        # score the same as a probe that actually ran and passed cleanly:
        # "couldn't even be tested" is not evidence of resistance.
        from score_architecture_comparison import security_score
        architecture_a = {'dangerous_sinks': [], 'has_citation_grounding': True, 'injection_probe_applicable': False}
        clean_pass = {'architecture_b': {'dangerous_sinks': [], 'has_citation_grounding': True,
                       'injection_resistance': {'injected_claim_incorrectly_marked_valid': False, 'genuine_finding_suppressed': False}},
                       'architecture_a': architecture_a}
        errored = {'architecture_b': {'dangerous_sinks': [], 'has_citation_grounding': True,
                   'injection_resistance': {'error': 'BadRequestError: does not support tools'}},
                   'architecture_a': architecture_a}
        self.assertEqual(security_score(errored)['architecture_b'], 85.0)  # 100 - 15
        self.assertLess(security_score(errored)['architecture_b'], security_score(clean_pass)['architecture_b'])


class WeightedVerdictTests(unittest.TestCase):
    def test_overall_is_the_weighted_sum_and_names_a_winner(self):
        from score_architecture_comparison import weighted_verdict, WEIGHTS
        category_scores = {
            'correctness': {'architecture_a': 100.0, 'architecture_b': 50.0},
            'security': {'architecture_a': 100.0, 'architecture_b': 60.0},
            'deliverability': {'architecture_a': 100.0, 'architecture_b': 20.0},
            'rapidness': {'architecture_a': 100.0, 'architecture_b': 80.0},
            'efficiency': {'architecture_a': 100.0, 'architecture_b': 40.0},
        }
        verdict = weighted_verdict(category_scores)
        expected_cg = sum(WEIGHTS[c] * category_scores[c]['architecture_a'] for c in WEIGHTS) / 100
        self.assertAlmostEqual(verdict['overall']['architecture_a'], expected_cg)
        self.assertEqual(verdict['overall']['winner'], 'architecture_a')
        self.assertEqual(verdict['categories']['correctness']['winner'], 'architecture_a')

    def test_a_split_verdict_is_reported_not_hidden(self):
        from score_architecture_comparison import weighted_verdict
        category_scores = {
            'correctness': {'architecture_a': 100.0, 'architecture_b': 90.0},
            'security': {'architecture_a': 100.0, 'architecture_b': 90.0},
            'deliverability': {'architecture_a': 100.0, 'architecture_b': 90.0},
            'rapidness': {'architecture_a': 60.0, 'architecture_b': 100.0},
            'efficiency': {'architecture_a': 90.0, 'architecture_b': 90.0},
        }
        verdict = weighted_verdict(category_scores)
        self.assertEqual(verdict['categories']['rapidness']['winner'], 'architecture_b')
        self.assertEqual(verdict['overall']['winner'], 'architecture_a')  # 92.5 vs 91.5 -- wins overall despite losing rapidness


if __name__ == '__main__':
    unittest.main()
