import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from facts_extractor import r003_details


class R003DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_clean_claim_passes(self):
        d = r003_details(self.c)
        self.assertEqual(d['facts'], ['R003:OK'])

    def test_boundary_date_passes(self):
        day = self.c['lines'][0]['service_date']
        self.c['coverage']['start_date'] = day
        self.c['coverage']['end_date'] = day
        d = r003_details(self.c)
        self.assertEqual(d['facts'], ['R003:OK'])

    def test_inactive_status_fails(self):
        self.c['coverage']['status'] = 'cancelled'
        d = r003_details(self.c)
        self.assertTrue(any(f.startswith('R003:INACTIVE:status=cancelled') for f in d['facts']))

    def test_out_of_period_fails(self):
        self.c['coverage']['start_date'] = '2026-01-01'
        self.c['coverage']['end_date'] = '2026-01-31'
        d = r003_details(self.c)
        self.assertTrue(any(f.startswith('R003:OUT_OF_PERIOD:/lines/0/service_date:') for f in d['facts']))
        self.assertIn('L1', d['line_ids'])

    def test_missing_end_date_is_unknown(self):
        self.c['coverage']['end_date'] = None
        d = r003_details(self.c)
        self.assertEqual(d['facts'], ['R003:UNKNOWN'])

    def test_known_failure_dominates_unknown(self):
        self.c['coverage']['end_date'] = None
        self.c['coverage']['status'] = 'cancelled'
        d = r003_details(self.c)
        self.assertTrue(any(f.startswith('R003:INACTIVE:') for f in d['facts']))

    def test_line_ids_preserve_index_order_not_sorted(self):
        # Two out-of-period lines whose line_ids sort the opposite way from
        # their index order — line_ids must come back in index order (['L9',
        # 'L1']), matching engine_core.base_check exactly. A sorted-by-id
        # implementation would wrongly return ['L1', 'L9'].
        self.c['lines'][0]['line_id'] = 'L9'
        second = copy.deepcopy(self.c['lines'][1])
        second['line_id'] = 'L1'
        self.c['lines'] = [self.c['lines'][0], second]
        self.c['coverage']['start_date'] = '2026-01-01'
        self.c['coverage']['end_date'] = '2026-01-02'
        d = r003_details(self.c)
        self.assertEqual(d['line_ids'], ['L9', 'L1'])


if __name__ == '__main__':
    unittest.main()
