import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config
from facts_extractor import r013_details


class R013DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']
        cls.cfg = config(ROOT)

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_clean_claim_passes(self):
        d = r013_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R013:OK'])

    def test_zero_quantity_fails(self):
        self.c['lines'][0]['quantity'] = 0
        d = r013_details(self.c, self.cfg)
        self.assertTrue(any(f.startswith('R013:LIMIT:') for f in d['facts']))
        self.assertIn('L1', d['line_ids'])

    def test_price_over_policy_max_fails(self):
        self.c['lines'][0]['unit_price'] = 9999  # SVC-LAB max is 260
        d = r013_details(self.c, self.cfg)
        self.assertTrue(any(f.startswith('R013:LIMIT:') for f in d['facts']))

    def test_quantity_over_policy_max_fails(self):
        self.c['lines'][0]['quantity'] = 99  # SVC-LAB max_quantity_per_line is 3
        d = r013_details(self.c, self.cfg)
        self.assertTrue(any(f.startswith('R013:LIMIT:') for f in d['facts']))

    def test_equality_at_max_passes(self):
        self.c['lines'][0]['quantity'] = 3
        self.c['lines'][0]['unit_price'] = 260
        self.c['lines'][0]['net_amount'] = 780
        d = r013_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R013:OK'])

    def test_missing_quantity_is_unknown(self):
        self.c['lines'][0]['quantity'] = None
        d = r013_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R013:UNKNOWN'])

    def test_unavailable_policy_is_unknown(self):
        self.c['policy_id'] = 'EDU-NOPE'
        d = r013_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R013:UNKNOWN'])


if __name__ == '__main__':
    unittest.main()
