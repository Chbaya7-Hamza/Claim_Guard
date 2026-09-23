import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from facts_extractor import r002_details


class R002DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_clean_claim_passes(self):
        d = r002_details(self.c)
        self.assertEqual(d['facts'], ['R002:OK'])

    def test_service_after_submission_fails(self):
        self.c['submission_date'] = '2026-05-01'
        d = r002_details(self.c)
        self.assertTrue(any(f.startswith('R002:LATE:/lines/0/service_date') for f in d['facts']))
        self.assertIn('L1', d['line_ids'])

    def test_equal_dates_pass(self):
        self.c['submission_date'] = self.c['lines'][1]['service_date']
        self.c['lines'][0]['service_date'] = self.c['lines'][1]['service_date']
        d = r002_details(self.c)
        self.assertEqual(d['facts'], ['R002:OK'])

    def test_missing_service_date_is_unknown(self):
        self.c['lines'][0]['service_date'] = None
        d = r002_details(self.c)
        self.assertEqual(d['facts'], ['R002:UNKNOWN'])

    def test_known_failure_dominates_unknown(self):
        self.c['lines'][0]['service_date'] = None
        self.c['submission_date'] = '2026-05-01'
        d = r002_details(self.c)
        self.assertTrue(any(f.startswith('R002:LATE:') for f in d['facts']))


if __name__ == '__main__':
    unittest.main()
