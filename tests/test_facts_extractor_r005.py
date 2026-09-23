import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config
from facts_extractor import r005_details


class R005DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']
        cls.cfg = config(ROOT)

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_clean_claim_passes(self):
        d = r005_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R005:OK'])

    def test_unlisted_provider_fails(self):
        self.c['provider_id'] = 'EDU-PROV-99'
        d = r005_details(self.c, self.cfg)
        self.assertTrue(any(f.startswith('R005:UNLISTED:') for f in d['facts']))

    def test_missing_provider_is_unknown(self):
        self.c['provider_id'] = None
        d = r005_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R005:UNKNOWN'])

    def test_unknown_policy_is_unknown(self):
        self.c['policy_id'] = 'EDU-NOPE'
        d = r005_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R005:UNKNOWN'])


if __name__ == '__main__':
    unittest.main()
