"""Phase 1 rubric checks that a grader's script could literally run.

Ingestion: an Encounter carried by a bundle is ingested and reported, not dropped.
Structured output: every result the engine emits validates against schemas/result.schema.json
and carries the rubric's named fields, on all three public splits.
"""
import copy
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config
from fhir_adapter import bundle_to_claim
from schema_subset import validate
from yara_engine import evaluate

SPLITS = ('development', 'validation', 'stress')
RESULT_SCHEMA = json.loads((ROOT / 'schemas' / 'result.schema.json').read_text(encoding='utf-8'))
# Rubric wording -> the schema field that carries it.
RUBRIC_FIELDS = {'Claim ID': 'claim_id', 'Rule ID': 'rule_id', 'rule-linked evidence': 'evidence',
                 'severity level': 'severity', 'confidence score': 'confidence',
                 'suggested corrective action': 'corrective_action'}


def load(path):
    return [json.loads(l) for l in (ROOT / path).read_text(encoding='utf-8').splitlines() if l.strip()]


def bundle_with_encounter(**overrides):
    bundle = copy.deepcopy(load('data/development/fhir_bundles.jsonl')[0])
    claim_res = next(e['resource'] for e in bundle['entry'] if e['resource']['resourceType'] == 'Claim')
    patient_ref = claim_res['patient']['reference']
    enc = {'resourceType': 'Encounter', 'id': 'ENC-1', 'status': 'finished',
           'class': {'code': 'AMB'}, 'subject': {'reference': patient_ref},
           'serviceProvider': claim_res['provider'],
           'period': {'start': '2026-05-25', 'end': '2026-05-25'}}
    enc.update(overrides)
    bundle['entry'].append({'fullUrl': 'https://claimguard.example/fhir/Encounter/ENC-1', 'resource': enc})
    for it in claim_res['item']:
        it['encounter'] = [{'reference': 'https://claimguard.example/fhir/Encounter/ENC-1'}]
    return bundle


class EncounterIngestionTests(unittest.TestCase):
    def test_the_supplied_pack_has_no_encounter_and_reports_none(self):
        for s in SPLITS:
            for b in load(f'data/{s}/fhir_bundles.jsonl'):
                self.assertNotIn('Encounter', {e['resource']['resourceType'] for e in b['entry']})
                self.assertEqual(bundle_to_claim(b)[1]['encounters'], [])

    def test_an_encounter_in_a_bundle_is_ingested_and_reported(self):
        claim, report = bundle_to_claim(bundle_with_encounter())
        self.assertEqual(len(report['encounters']), 1)
        enc = report['encounters'][0]
        self.assertEqual((enc['encounter_id'], enc['status'], enc['class']), ('ENC-1', 'finished', 'AMB'))
        self.assertEqual((enc['period_start'], enc['period_end']), ('2026-05-25', '2026-05-25'))
        self.assertEqual(enc['patient_id'], claim['patient_id'])
        self.assertEqual(report['warnings'], [])

    def test_the_claim_envelope_is_unchanged_by_an_encounter(self):
        with_enc, _ = bundle_to_claim(bundle_with_encounter())
        without, _ = bundle_to_claim(load('data/development/fhir_bundles.jsonl')[0])
        self.assertEqual(with_enc, without)
        self.assertNotIn('encounter', with_enc)

    def test_an_encounter_for_a_different_patient_is_a_warning_not_silence(self):
        bundle = bundle_with_encounter()
        enc = next(e['resource'] for e in bundle['entry'] if e['resource']['resourceType'] == 'Encounter')
        enc['subject'] = {'reference': 'https://claimguard.example/fhir/Patient/PAT-OTHER'}
        _, report = bundle_to_claim(bundle)
        self.assertTrue(any(w.startswith('encounter_patient_mismatch') for w in report['warnings']), report['warnings'])

    def test_a_line_pointing_at_a_missing_encounter_is_reported(self):
        bundle = bundle_with_encounter()
        bundle['entry'] = [e for e in bundle['entry'] if e['resource']['resourceType'] != 'Encounter']
        _, report = bundle_to_claim(bundle)
        self.assertTrue(any('Claim.item.encounter' in w for w in report['warnings']), report['warnings'])


class StructuredOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = config(ROOT)
        cls.rows = []
        cls.claims = 0
        for s in SPLITS:
            for claim in load(f'data/{s}/claims.jsonl'):
                cls.claims += 1
                cls.rows.extend(evaluate(claim, cfg))

    def test_every_result_on_every_public_split_validates_against_the_result_schema(self):
        for r in self.rows:
            validate(r, RESULT_SCHEMA)
        self.assertEqual(len(self.rows), self.claims * 15)

    def test_each_claim_gets_exactly_one_result_per_rule(self):
        per_claim = Counter(r['claim_id'] for r in self.rows)
        self.assertEqual(set(per_claim.values()), {15})
        self.assertEqual(len({(r['claim_id'], r['rule_id']) for r in self.rows}), len(self.rows))

    def test_the_rubric_fields_exist_on_every_result_under_their_exact_names(self):
        for r in self.rows:
            for wording, field in RUBRIC_FIELDS.items():
                self.assertIn(field, r, wording)

    def test_a_failing_result_names_evidence_severity_and_an_action(self):
        fails = [r for r in self.rows if r['status'] == 'FAIL']
        self.assertGreater(len(fails), 0)
        for r in fails:
            self.assertTrue(r['evidence'] and r['corrective_action'].strip(), r['rule_id'])
            self.assertIn(r['severity'], {'high', 'medium', 'low'})

    def test_confidence_follows_the_rulebook_null_and_not_probabilistic_for_rules(self):
        # docs/04_Rulebook.md: "Deterministic checks use confidence=null and confidence_kind=not_probabilistic."
        self.assertEqual({(r['confidence'], r['confidence_kind']) for r in self.rows}, {(None, 'not_probabilistic')})
        answer_key = {(r['confidence'], r['confidence_kind'])
                      for r in load('data/development/expected_results.jsonl')}
        self.assertEqual(answer_key, {(None, 'not_probabilistic')})


if __name__ == '__main__':
    unittest.main()
