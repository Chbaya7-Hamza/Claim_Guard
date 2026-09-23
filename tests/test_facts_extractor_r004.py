import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from facts_extractor import r004_details


class R004DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_clean_claim_passes(self):
        d = r004_details(self.c)
        self.assertEqual(d['facts'], ['R004:OK'])

    def test_patient_mismatch_fails(self):
        self.c['patient_id'] = 'PAT-DIFFERENT'
        d = r004_details(self.c)
        self.assertTrue(any(f.startswith('R004:PATIENT_MISMATCH:') for f in d['facts']))

    def test_member_mismatch_fails(self):
        self.c['member_id'] = 'MEM-DIFFERENT'
        d = r004_details(self.c)
        self.assertTrue(any(f.startswith('R004:MEMBER_MISMATCH:') for f in d['facts']))

    def test_missing_beneficiary_is_unknown(self):
        self.c['coverage']['beneficiary_patient_id'] = None
        d = r004_details(self.c)
        self.assertEqual(d['facts'], ['R004:UNKNOWN'])

    def test_known_failure_dominates_unknown(self):
        self.c['coverage']['member_id'] = None
        self.c['patient_id'] = 'PAT-DIFFERENT'
        d = r004_details(self.c)
        self.assertTrue(any(f.startswith('R004:PATIENT_MISMATCH:') for f in d['facts']))


if __name__ == '__main__':
    unittest.main()
