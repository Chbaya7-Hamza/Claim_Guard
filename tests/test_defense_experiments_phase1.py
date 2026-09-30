"""The Phase 1 decision experiments (docs/27) as regression tests: each asserts the property the decision rests on, on small inputs, so a
change that breaks the property fails the suite instead of silently invalidating the recorded numbers."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src'))

import tempfile  # noqa: E402

import defense_experiments as de  # noqa: E402

_TMP = tempfile.TemporaryDirectory()


def setUpModule():
    # the experiments write their results to OUT; a test run must never overwrite the recorded evidence in outputs/defense/
    de.OUT = Path(_TMP.name)


def tearDownModule():
    _TMP.cleanup()


class QuarantineTests(unittest.TestCase):
    def test_damaged_records_never_stop_the_batch_or_reach_the_rules(self):
        r = de.quarantine(n_valid=12, copies=1)['claimguard']
        self.assertTrue(r['every_record_accounted_for'])
        self.assertEqual(r['quarantined_records_that_reached_the_rules'], 0)
        self.assertEqual(r['sound_claims_with_unchanged_verdicts'], '12 of 12')
        self.assertFalse(r['wrong_typed_amount_records_accepted_by_design']['any_PASS_on_R012'])


class ReviewWorkflowTests(unittest.TestCase):
    def test_no_invalid_decision_is_accepted_and_a_bad_batch_writes_nothing(self):
        r = de.review(n_claims=8)
        self.assertEqual(r['valid_decisions_accepted']['accepted'], r['valid_decisions_accepted']['of'])
        self.assertTrue(all(v['wrongly_accepted'] == 0 for v in r['invalid_decisions_wrongly_accepted'].values()))
        self.assertEqual(r['decision_on_a_PASS_finding']['wrongly_accepted'], 0)
        b = r['batch_with_one_bad_decision']
        self.assertTrue(b['rejected_whole_batch'])
        self.assertEqual(b['log_rows_before'], b['log_rows_after'])
        rc = r['recheck']
        self.assertEqual(rc['original_claim_and_results_untouched'], rc['claims_rechecked'])
        self.assertEqual(rc['still_failing_finding_back_to_unreviewed'], rc['claims_rechecked'])


class InputLimitTests(unittest.TestCase):
    def test_limits_leave_real_data_alone_and_stop_a_hostile_claim(self):
        r = de.limits()
        self.assertEqual(r['findings_over_the_prompt_limit'], 0)
        self.assertLess(r['prompt_chars']['max'], r['limit_chars'])
        self.assertIn('exceeds the', r['hostile_5000_line_claim']['failed_closed_to_template'])


class IngestFormatTests(unittest.TestCase):
    def test_csv_is_identical_and_fhir_never_creates_a_silent_pass(self):
        r = de.ingestformats()['splits']
        for split in r.values():
            self.assertEqual(split['csv_folder']['verdict_agreement_percent'], 100.0)
            self.assertEqual(split['csv_folder']['claims_field_identical_to_jsonl'], split['csv_folder']['accepted'])
            self.assertEqual(split['fhir_bundle']['silent_passes'], 0)
            self.assertTrue(all(k.startswith('R009') for k in split['fhir_bundle']['differences']))


if __name__ == '__main__':
    unittest.main()
