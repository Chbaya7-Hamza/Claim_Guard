import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from facts_extractor import r001_details


class R001DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_clean_claim_passes(self):
        d = r001_details(self.c)
        self.assertEqual(d['facts'], ['R001:OK'])
        self.assertEqual(d['evidence_paths'], ['/invoice_number', '/member_id', '/diagnosis_code', '/lines'])
        self.assertEqual(d['line_ids'], [])
        self.assertEqual(d['message'], 'Required information is present.')

    def test_missing_top_level_field(self):
        self.c['invoice_number'] = None
        d = r001_details(self.c)
        self.assertEqual(d['facts'], ['R001:MISSING:/invoice_number'])
        self.assertEqual(d['evidence_paths'], ['/invoice_number'])
        self.assertEqual(d['message'], 'Required information is missing.')

    def test_missing_line_field_reports_line_id(self):
        self.c['lines'][0]['quantity'] = None
        d = r001_details(self.c)
        self.assertIn('R001:MISSING:/lines/0/quantity', d['facts'])
        self.assertEqual(d['line_ids'], ['L1'])


if __name__ == '__main__':
    unittest.main()
