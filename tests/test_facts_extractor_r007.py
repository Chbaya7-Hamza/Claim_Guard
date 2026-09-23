import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from facts_extractor import r007_details


class R007DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_clean_claim_passes(self):
        d = r007_details(self.c)
        self.assertEqual(d['facts'], ['R007:OK'])

    def test_wrong_net_amount_fails(self):
        self.c['lines'][0]['net_amount'] = 999
        d = r007_details(self.c)
        self.assertTrue(any(f.startswith('R007:MISMATCH:/lines/0/net_amount') for f in d['facts']))
        self.assertIn('L1', d['line_ids'])

    def test_rounding_tolerance_passes(self):
        self.c['lines'][0]['quantity'] = 3
        self.c['lines'][0]['unit_price'] = 33.335
        self.c['lines'][0]['net_amount'] = 100.01  # 3 * 33.335 = 100.005 -> rounds to 100.01 or 100.00, within 0.01
        d = r007_details(self.c)
        self.assertEqual(d['facts'], ['R007:OK'])

    def test_missing_quantity_is_unknown(self):
        self.c['lines'][0]['quantity'] = None
        d = r007_details(self.c)
        self.assertEqual(d['facts'], ['R007:UNKNOWN'])

    def test_known_failure_dominates_unknown(self):
        self.c['lines'][0]['quantity'] = None
        self.c['lines'][1]['net_amount'] = 999
        d = r007_details(self.c)
        self.assertTrue(any(f.startswith('R007:MISMATCH:') for f in d['facts']))


if __name__ == '__main__':
    unittest.main()
