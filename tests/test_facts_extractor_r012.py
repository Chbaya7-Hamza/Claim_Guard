import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from facts_extractor import r012_details


class R012DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_clean_claim_passes(self):
        d = r012_details(self.c)
        self.assertEqual(d['facts'], ['R012:OK'])

    def test_wrong_total_fails(self):
        self.c['total_amount'] = 999
        d = r012_details(self.c)
        self.assertTrue(any(f.startswith('R012:MISMATCH:') for f in d['facts']))

    def test_missing_total_is_unknown(self):
        self.c['total_amount'] = None
        d = r012_details(self.c)
        self.assertEqual(d['facts'], ['R012:UNKNOWN'])

    def test_missing_line_amount_is_unknown(self):
        self.c['lines'][0]['net_amount'] = None
        d = r012_details(self.c)
        self.assertEqual(d['facts'], ['R012:UNKNOWN'])


if __name__ == '__main__':
    unittest.main()
