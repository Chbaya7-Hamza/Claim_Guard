"""Garbled model output must not reach a reviewer.

Found by the experiments in docs/21: the hosted 14B model sometimes derails in the middle of a reply. Three such
explanations (mixed-language gibberish inside otherwise valid JSON) were accepted as live answers because the schema and the
grounding guard only looked at structure, citations and a few phrases. The guard now rejects text in another script, a
replacement character, and long repetitions, and the recorded experiment data is the false-positive check.
"""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from llm_adapter import MockExplanationProvider, check_grounding, explain_with_fallback

FINDING = {'claim_id': 'CG-1', 'rule_id': 'R001', 'status': 'FAIL', 'requires_human_review': True,
           'explanation': 'Required information is missing.',
           'evidence': [{'path': '/invoice_number', 'value': None}]}
RULE = {'rule_id': 'R001', 'title': 'Required claim information'}


def out(text):
    return {'explanation': text, 'cited_evidence_paths': ['/invoice_number'], 'cited_rule_ids': ['R001'],
            'needs_human_review': True}


GARBLED = {
    'cjk in the middle': 'The service date is April 2 ' + chr(0x6570) * 3 + chr(0x4e0b) + ' 27, 2026, which is after submission.',
    'cyrillic': 'The invoice number is missing ' + chr(0x0440) + chr(0x0430) + chr(0x0441) + ' for this claim.',
    'arabic': 'Missing information ' + chr(0x0623) + chr(0x0641) + chr(0x0644) + ' on the invoice.',
    'replacement character': 'The invoice number ' + chr(0xfffd) + ' is missing.',
    'fullwidth bracket': 'The provider ' + chr(0x3010) + 'ICD is not listed.',
    'one character repeated': 'The invoice number is missing ' + '!' * 30,
    'one word repeated': 'The invoice number is missing. ' + 'the ' * 12,
}


class GarbledOutputGuard(unittest.TestCase):
    def test_a_plain_english_explanation_passes(self):
        check_grounding(out('The invoice number is missing, so the required-information check failed.'), FINDING, RULE)

    def test_common_punctuation_and_accents_are_not_mistaken_for_garbage(self):
        text = ('The provider "EDU-PROV-01" isn’t listed — a café-style name (née José) or 3° value, '
                'quantity 2–2, "quoted" text…')
        check_grounding(out(text), FINDING, RULE)

    def test_every_kind_of_garbled_text_is_rejected(self):
        for label, text in GARBLED.items():
            with self.subTest(label), self.assertRaisesRegex(ValueError, 'garbled text'):
                check_grounding(out(text), FINDING, RULE)

    def test_a_character_that_is_already_in_the_supplied_finding_is_allowed(self):
        finding = copy.deepcopy(FINDING)
        finding['evidence'] = [{'path': '/invoice_number', 'value': 'INV-' + chr(0x6570)}]
        check_grounding(out('The invoice number INV-' + chr(0x6570) + ' was submitted.'), finding, RULE)

    def test_the_pipeline_replaces_a_garbled_reply_with_the_template(self):
        class Garbled:
            def explain(self, finding, rule, untrusted_note=None):
                return out(GARBLED['cjk in the middle'])

        result, used_fallback, error, _ = explain_with_fallback(Garbled(), MockExplanationProvider(), FINDING, RULE)
        self.assertTrue(used_fallback)
        self.assertIn('garbled', error)
        self.assertEqual(result['explanation'], FINDING['explanation'])


class RecordedExperimentData(unittest.TestCase):
    """About 1,500 recorded live answers: the guard must reject the garbled ones and nothing else."""

    def test_the_guard_rejects_the_recorded_garbled_answers_and_no_clean_one(self):
        raw = ROOT / 'experiments' / 'raw'
        files = sorted(raw.glob('e*.jsonl')) if raw.exists() else []
        if not files:
            self.skipTest('no recorded experiment data')
        cases = {}
        for name in ('llm_explanation_cases.jsonl', 'injection_variants.jsonl', 'fresh_variants.jsonl', 'fresh2_variants.jsonl', 'fresh3_variants.jsonl', 'fresh4_variants.jsonl'):
            for line in (ROOT / 'exercises' / name).read_text(encoding='utf-8').split(chr(10)):
                if line.strip():
                    c = json.loads(line)
                    cases[c['case_id']] = c
        checked = rejected = 0
        for path in files:
            for line in path.read_text(encoding='utf-8').split(chr(10)):
                if not line.strip():
                    continue
                rec = json.loads(line)
                if rec.get('type') != 'call' or rec['outcome'] != 'live':
                    continue
                case = cases[rec['case_id']]
                reply = out(rec['explanation'])
                reply['cited_evidence_paths'] = rec['cited_paths']
                reply['cited_rule_ids'] = rec['cited_rules']
                checked += 1
                try:
                    check_grounding(reply, case['finding'], case['rule'])
                except ValueError as e:
                    rejected += 1
                    self.assertIn('garbled', str(e), f'{rec["case_id"]}: guard rejected a clean answer: {e}')
        self.assertGreater(checked, 1000)
        self.assertGreaterEqual(rejected, 3, 'the three garbled answers that were once accepted must now be rejected')


if __name__ == '__main__':
    unittest.main()
