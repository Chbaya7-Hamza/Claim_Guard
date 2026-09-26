"""Formatting slips in cited_evidence_paths are repaired; nothing else is.

The recorded experiments showed the biggest cause of rejected model replies was a cited path that was not exactly one of the
finding's evidence paths (a dropped letter, a stray space, a more specific path under an allowed one). The repair maps such a
slip to the one allowed path it obviously means, records every repair, and never touches the text, the rule id or the review
flag. Replies whose paths cannot be mapped are still rejected.
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))
from audit_log import AuditLog, audited_review, verify_ai_ordering, verify_with_anchor
from claim_review import draft_and_validate_explanation
from engine_core import config
from llm_adapter import (MockExplanationProvider, check_grounding, explain_with_fallback, repair_citations,
                         take_citation_repairs, validate_explanation)
from test_stress_boundaries import CLEAN

FINDING = {'claim_id': 'CG-1', 'rule_id': 'R003', 'status': 'FAIL', 'requires_human_review': True,
           'explanation': 'Service date outside the coverage period.',
           'evidence': [{'path': '/coverage/end_date', 'value': '2026-04-29'},
                        {'path': '/lines/0/service_date', 'value': '2026-04-30'},
                        {'path': '/authorizations/0', 'value': {'max_quantity': 1}}]}
RULE = {'rule_id': 'R003', 'title': 'Coverage active on service date'}


def reply(paths, text='Rule R003 failed because the service is after the coverage end. The evidence shows /coverage/end_date is 2026-04-29. Verify coverage.'):
    return {'explanation': text, 'cited_evidence_paths': paths, 'cited_rule_ids': ['R003'], 'needs_human_review': True}


class Repair(unittest.TestCase):
    def setUp(self):
        take_citation_repairs()

    def fixed(self, paths):
        out = repair_citations(reply(paths), FINDING)
        return out['cited_evidence_paths'], take_citation_repairs()

    def test_a_correct_reply_is_untouched_and_reports_nothing(self):
        out = repair_citations(reply(['/coverage/end_date']), FINDING)
        self.assertEqual(out['cited_evidence_paths'], ['/coverage/end_date'])
        self.assertEqual(take_citation_repairs(), [])

    def test_a_dropped_character_is_mapped_to_the_one_path_it_means(self):
        paths, notes = self.fixed(['/coverage/end_ate'])
        self.assertEqual(paths, ['/coverage/end_date'])
        self.assertEqual(notes, [{'from': '/coverage/end_ate', 'to': '/coverage/end_date', 'kind': 'typo'}])

    def test_a_dropped_leading_slash_is_a_one_character_slip(self):
        paths, notes = self.fixed(['coverage/end_date'])
        self.assertEqual((paths, notes[0]['kind']), (['/coverage/end_date'], 'typo'))

    def test_a_stray_space_is_removed(self):
        paths, notes = self.fixed(['/lines/0/ service_date'])
        self.assertEqual((paths, notes[0]['kind']), (['/lines/0/service_date'], 'whitespace'))

    def test_a_more_specific_path_maps_to_the_allowed_path_it_lies_under(self):
        paths, notes = self.fixed(['/authorizations/0/max_quantity'])
        self.assertEqual((paths, notes[0]['kind']), (['/authorizations/0'], 'ancestor'))

    def test_repaired_duplicates_collapse(self):
        paths, _ = self.fixed(['/authorizations/0', '/authorizations/0/max_quantity'])
        self.assertEqual(paths, ['/authorizations/0'])

    def test_a_path_that_means_nothing_allowed_is_left_for_the_schema_to_reject(self):
        for bad in ('/approved_by_payer', '/lines/0/quantity', '/coverage', '/', ''):
            out = repair_citations(reply([bad]), FINDING)
            self.assertEqual(out['cited_evidence_paths'], [bad], bad)
            with self.assertRaises(ValueError):
                validate_explanation(out, FINDING)
        self.assertEqual(take_citation_repairs(), [])

    def test_an_ambiguous_typo_is_not_guessed(self):
        finding = copy.deepcopy(FINDING)
        finding['evidence'] = [{'path': '/a/x1', 'value': 1}, {'path': '/a/x2', 'value': 2}]
        out = repair_citations(reply(['/a/x']), finding)  # one edit from both
        self.assertEqual(out['cited_evidence_paths'], ['/a/x'])

    def test_nothing_but_the_paths_can_change(self):
        original = reply(['/coverage/end_ate'])
        snapshot = copy.deepcopy(original)
        out = repair_citations(original, FINDING)
        self.assertEqual(original, snapshot)  # the input is not edited in place
        for key in ('explanation', 'cited_rule_ids', 'needs_human_review'):
            self.assertEqual(out[key], snapshot[key])

    def test_a_relabelled_reply_is_still_rejected_after_repair(self):
        for bad in (dict(reply(['/coverage/end_ate']), cited_rule_ids=['R999']),
                    dict(reply(['/coverage/end_ate']), needs_human_review=False),
                    dict(reply(['/coverage/end_ate']), extra='x')):
            with self.assertRaises(ValueError):
                validate_explanation(repair_citations(bad, FINDING), FINDING)

    def test_non_dict_and_odd_citation_shapes_pass_through(self):
        for odd in (None, 'text', [], {'cited_evidence_paths': 'x'}, {'cited_evidence_paths': [1, 2]}, {}):
            self.assertEqual(repair_citations(odd, FINDING), odd)

    def test_the_grounding_guard_still_applies_after_a_repair(self):
        garbled = reply(['/coverage/end_ate'], text='Rule R003 failed ' + chr(0x6570) + chr(0x4e0b) + ' badly.')
        with self.assertRaises(ValueError):
            check_grounding(validate_explanation(repair_citations(garbled, FINDING), FINDING), FINDING, RULE)


class RepairInThePipeline(unittest.TestCase):
    class Provider:
        model = 'stub'

        def __init__(self, paths):
            self.paths = paths

        def explain(self, finding, rule, untrusted_note=None):
            return reply(self.paths)

    def test_a_slip_no_longer_costs_the_reviewer_the_explanation(self):
        result, used_fallback, error, _ = explain_with_fallback(self.Provider(['/coverage/end_ate']), MockExplanationProvider(),
                                                                copy.deepcopy(FINDING), RULE)
        self.assertFalse(used_fallback, error)
        self.assertEqual(result['cited_evidence_paths'], ['/coverage/end_date'])

    def test_draft_and_validate_reports_the_repair(self):
        out = draft_and_validate_explanation(copy.deepcopy(FINDING), RULE, self.Provider(['/lines/0/ service_date']),
                                             MockExplanationProvider())
        self.assertFalse(out['used_fallback'])
        self.assertEqual([r['kind'] for r in out['citation_repairs']], ['whitespace'])

    def test_a_reply_that_needed_no_repair_reports_none_and_a_fallback_reports_none(self):
        ok = draft_and_validate_explanation(copy.deepcopy(FINDING), RULE, self.Provider(['/coverage/end_date']), MockExplanationProvider())
        self.assertEqual(ok['citation_repairs'], [])
        bad = draft_and_validate_explanation(copy.deepcopy(FINDING), RULE, self.Provider(['/nonsense']), MockExplanationProvider())
        self.assertTrue(bad['used_fallback'])
        self.assertEqual(bad['citation_repairs'], [])

    def test_repairs_do_not_leak_between_calls(self):
        draft_and_validate_explanation(copy.deepcopy(FINDING), RULE, self.Provider(['/coverage/end_ate']), MockExplanationProvider())
        again = draft_and_validate_explanation(copy.deepcopy(FINDING), RULE, self.Provider(['/coverage/end_date']), MockExplanationProvider())
        self.assertEqual(again['citation_repairs'], [])

    def test_the_audit_log_records_the_repair_and_still_verifies(self):
        cfg = config(ROOT)
        claim = copy.deepcopy(CLEAN)
        claim['total_amount'] = 1.0  # R012 FAIL, evidence /total_amount and the line amounts

        class Slip:
            model = 'stub'

            def explain(self, finding, rule, untrusted_note=None):
                return {'explanation': 'Rule R012 failed because the claim total differs from the line amounts. The evidence shows /total_amount is 1.0. Verify the total against the source record.',
                        'cited_evidence_paths': ['/total_amoun'], 'cited_rule_ids': ['R012'], 'needs_human_review': True}

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.jsonl'
            audited_review(AuditLog(path), claim, cfg, provider=Slip(), fallback=MockExplanationProvider())
            verify_with_anchor(path)
            verify_ai_ordering(path)
            events = [json.loads(l)['event'] for l in path.read_text(encoding='utf-8').split(chr(10)) if l.strip()]
        rec = next(e for e in events if e['event_type'] == 'ai_recommendation')
        self.assertFalse(rec['used_fallback'])
        self.assertEqual(rec['model'], 'stub')
        self.assertEqual(rec['citation_repairs'], [{'from': '/total_amoun', 'to': '/total_amount', 'kind': 'typo'}])


class RecordedRejections(unittest.TestCase):
    """The recorded model replies that were rejected for a bad citation are the safety check for the repair."""

    def test_the_repair_recovers_most_recorded_bad_citations_and_never_a_relabelled_reply(self):
        raw = ROOT / 'experiments' / 'raw'
        # Only runs made before the repair existed: in round four (e10*) the repair was already on, so what is rejected there is
        # by construction what it could not fix.
        files = [p for p in sorted(raw.glob('e*.jsonl')) if not p.stem.startswith('e10')] if raw.exists() else []
        if not files:
            self.skipTest('no recorded experiment data')
        cases = {}
        for name in ('llm_explanation_cases.jsonl', 'injection_variants.jsonl', 'fresh_variants.jsonl', 'fresh2_variants.jsonl',
                     'fresh3_variants.jsonl', 'fresh4_variants.jsonl'):
            path = ROOT / 'exercises' / name
            if path.exists():
                for line in path.read_text(encoding='utf-8').split(chr(10)):
                    if line.strip():
                        c = json.loads(line)
                        cases[c['case_id']] = c
        total = recovered = 0
        for path in files:
            for line in path.read_text(encoding='utf-8').split(chr(10)):
                if not line.strip():
                    continue
                rec = json.loads(line)
                if rec.get('type') != 'call' or rec['outcome'] != 'model_rejected' or not rec.get('raw_replies'):
                    continue
                if 'evidence citation' not in (rec['error'] or ''):
                    continue
                case = cases.get(rec['case_id'])
                try:
                    original = json.loads(rec['raw_replies'][-1])
                except ValueError:
                    continue
                if case is None or not isinstance(original, dict):
                    continue
                total += 1
                take_citation_repairs()
                try:
                    out = check_grounding(validate_explanation(repair_citations(original, case['finding']), case['finding']),
                                          case['finding'], case['rule'])
                except ValueError:
                    continue
                recovered += 1
                self.assertEqual(out['needs_human_review'], case['finding']['requires_human_review'])
                self.assertEqual(out['cited_rule_ids'], [case['finding']['rule_id']])
        self.assertGreater(total, 40)
        self.assertGreaterEqual(recovered / total, 0.9, f'{recovered} of {total} recovered')


if __name__ == '__main__':
    unittest.main()
