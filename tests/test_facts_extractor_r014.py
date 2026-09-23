import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config
from facts_extractor import r014_details


class R014DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']
        cls.cfg = config(ROOT)

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_clean_claim_passes(self):
        # policy_id is EDU-PLUS (60-day window); service dates 2026-05-25, submission 2026-06-06 -> lag=12
        d = r014_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R014:OK'])

    def test_equality_at_window_passes(self):
        self.c['submission_date'] = '2026-07-24'  # 2026-05-25 + 60 days
        d = r014_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R014:OK'])

    def test_over_window_fails(self):
        self.c['submission_date'] = '2026-07-25'  # 61 days
        d = r014_details(self.c, self.cfg)
        self.assertTrue(any(f.startswith('R014:LATE:') for f in d['facts']))

    def test_negative_lag_is_not_applicable(self):
        self.c['submission_date'] = '2026-05-01'  # before the service dates
        d = r014_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R014:NOT_APPLICABLE'])

    def test_missing_policy_is_unknown(self):
        self.c['policy_id'] = 'EDU-NOPE'
        d = r014_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R014:UNKNOWN'])


if __name__ == '__main__':
    unittest.main()
