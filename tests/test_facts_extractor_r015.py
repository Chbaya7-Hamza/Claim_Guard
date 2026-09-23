import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config
from facts_extractor import r015_details


class R015DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']
        cls.cfg = config(ROOT)

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_clean_claim_passes(self):
        d = r015_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R015:OK'])

    def test_wrong_currency_fails(self):
        self.c['currency'] = 'USD'
        d = r015_details(self.c, self.cfg)
        self.assertTrue(any(f.startswith('R015:MISMATCH:') for f in d['facts']))

    def test_missing_currency_is_unknown(self):
        self.c['currency'] = None
        d = r015_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R015:UNKNOWN'])

    def test_unavailable_policy_is_unknown(self):
        self.c['policy_id'] = 'EDU-NOPE'
        d = r015_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R015:UNKNOWN'])


if __name__ == '__main__':
    unittest.main()
