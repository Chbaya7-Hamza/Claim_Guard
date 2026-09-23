import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config
from facts_extractor import r008_details


def image_line(line_id='L3', authorization_id=None):
    return {
        'line_id': line_id, 'service_code': 'SVC-IMAGE', 'service_date': '2026-05-25',
        'modifier': None, 'quantity': 1, 'unit_price': 1500, 'net_amount': 1500,
        'authorization_id': authorization_id,
    }


class R008DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']
        cls.cfg = config(ROOT)

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_no_auth_required_service_is_not_applicable(self):
        d = r008_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R008:NOT_APPLICABLE'])

    def test_auth_present_passes(self):
        self.c['lines'].append(image_line(authorization_id='AUTH-1'))
        d = r008_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R008:OK'])

    def test_missing_auth_fails(self):
        self.c['lines'].append(image_line(authorization_id=None))
        d = r008_details(self.c, self.cfg)
        self.assertTrue(any(f.startswith('R008:MISSING_AUTH:') for f in d['facts']))
        self.assertIn('L3', d['line_ids'])

    def test_uncatalogued_service_code_is_unknown(self):
        line = image_line(authorization_id='AUTH-1')
        line['service_code'] = 'SVC-UNLISTED'
        self.c['lines'].append(line)
        d = r008_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R008:UNKNOWN'])


if __name__ == '__main__':
    unittest.main()
