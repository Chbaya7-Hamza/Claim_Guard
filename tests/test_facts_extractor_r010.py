import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config
from facts_extractor import r010_details


def image_line(line_id='L3'):
    return {
        'line_id': line_id, 'service_code': 'SVC-IMAGE', 'service_date': '2026-05-25',
        'modifier': None, 'quantity': 1, 'unit_price': 1500, 'net_amount': 1500,
        'authorization_id': None,
    }


def doc(patient_id, service_code='SVC-IMAGE', service_date='2026-05-25', doc_type='imaging-report',
        document_status='final'):
    return {
        'attachment_id': 'DOC-1', 'type': doc_type, 'patient_id': patient_id,
        'service_code': service_code, 'service_date': service_date,
        'document_status': document_status, 'text': 'synthetic',
    }


class R010DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']
        cls.cfg = config(ROOT)

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_no_document_required_is_not_applicable(self):
        d = r010_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R010:NOT_APPLICABLE'])

    def test_final_matching_attachment_passes(self):
        self.c['lines'].append(image_line())
        self.c['attachments'].append(doc(self.c['patient_id']))
        d = r010_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R010:OK'])

    def test_draft_only_is_unable_to_assess(self):
        self.c['lines'].append(image_line())
        self.c['attachments'].append(doc(self.c['patient_id'], document_status='draft'))
        d = r010_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R010:UNKNOWN'])

    def test_no_matching_attachment_fails(self):
        self.c['lines'].append(image_line())
        d = r010_details(self.c, self.cfg)
        self.assertTrue(any(f.startswith('R010:MISSING_DOC:') for f in d['facts']))
        self.assertIn('L3', d['line_ids'])

    def test_uncatalogued_service_code_is_unknown(self):
        line = image_line()
        line['service_code'] = 'SVC-UNLISTED'
        self.c['lines'].append(line)
        d = r010_details(self.c, self.cfg)
        self.assertEqual(d['facts'], ['R010:UNKNOWN'])


if __name__ == '__main__':
    unittest.main()
