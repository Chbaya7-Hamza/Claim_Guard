import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config
from facts_extractor import r011_details


class R011DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']
        cls.cfg = config(ROOT)

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_clean_claim_passes(self):
        d = r011_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R011:OK'])

    def test_uncatalogued_code_fails(self):
        self.c['lines'][0]['service_code'] = 'SVC-UNLISTED'
        d = r011_details(self.c, self.cfg)
        self.assertTrue(any(f.startswith('R011:NOT_CATALOGUED:') for f in d['facts']))
        self.assertIn('L1', d['line_ids'])

    def test_missing_code_is_unknown(self):
        self.c['lines'][0]['service_code'] = None
        d = r011_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R011:UNKNOWN'])

    def test_known_failure_dominates_unknown(self):
        self.c['lines'][0]['service_code'] = None
        self.c['lines'][1]['service_code'] = 'SVC-UNLISTED'
        d = r011_details(self.c, self.cfg)
        self.assertTrue(any(f.startswith('R011:NOT_CATALOGUED:') for f in d['facts']))


if __name__ == '__main__':
    unittest.main()
