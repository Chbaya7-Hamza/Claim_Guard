import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config
from facts_extractor import r009_details


def image_line(line_id='L3', authorization_id=None):
    return {
        'line_id': line_id, 'service_code': 'SVC-IMAGE', 'service_date': '2026-05-25',
        'modifier': None, 'quantity': 1, 'unit_price': 1500, 'net_amount': 1500,
        'authorization_id': authorization_id,
    }


def auth(patient_id, authorization_id='AUTH-1', service_code='SVC-IMAGE', status='approved',
          valid_from='2026-01-01', valid_to='2026-12-31', max_quantity=10):
    return {
        'authorization_id': authorization_id, 'patient_id': patient_id, 'service_code': service_code,
        'status': status, 'valid_from': valid_from, 'valid_to': valid_to, 'max_quantity': max_quantity,
    }


class R009DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']
        cls.cfg = config(ROOT)

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_no_auth_required_service_is_not_applicable(self):
        d = r009_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R009:NOT_APPLICABLE'])

    def test_matching_authorization_passes(self):
        self.c['lines'].append(image_line(authorization_id='AUTH-1'))
        self.c['authorizations'].append(auth(self.c['patient_id']))
        d = r009_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R009:OK'])

    def test_unresolved_authorization_id_fails(self):
        self.c['lines'].append(image_line(authorization_id='AUTH-MISSING'))
        d = r009_details(self.c, self.cfg)
        self.assertTrue(any(f.startswith('R009:MISMATCH:') for f in d['facts']))
        self.assertIn('L3', d['line_ids'])

    def test_patient_mismatch_fails(self):
        self.c['lines'].append(image_line(authorization_id='AUTH-1'))
        self.c['authorizations'].append(auth('PAT-SOMEONE-ELSE'))
        d = r009_details(self.c, self.cfg)
        self.assertTrue(any(f.startswith('R009:MISMATCH:') for f in d['facts']))

    def test_quantity_over_max_fails(self):
        self.c['lines'].append(image_line(authorization_id='AUTH-1'))
        self.c['authorizations'].append(auth(self.c['patient_id'], max_quantity=0))
        d = r009_details(self.c, self.cfg)
        self.assertTrue(any(f.startswith('R009:MISMATCH:') for f in d['facts']))

    def test_missing_auth_id_is_unknown_not_fail(self):
        self.c['lines'].append(image_line(authorization_id=None))
        d = r009_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R009:UNKNOWN'])

    def test_uncatalogued_service_code_is_unknown(self):
        line = image_line(authorization_id='AUTH-1')
        line['service_code'] = 'SVC-UNLISTED'
        self.c['lines'].append(line)
        d = r009_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R009:UNKNOWN'])


if __name__ == '__main__':
    unittest.main()
