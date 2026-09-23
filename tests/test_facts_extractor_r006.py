import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from facts_extractor import r006_details, build_blob


class R006DetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def test_clean_claim_passes(self):
        d = r006_details(self.c)
        self.assertEqual(d['facts'], ['R006:OK'])
        self.assertEqual(d['evidence_paths'], ['/lines'])

    def test_duplicate_line_fails(self):
        other = copy.deepcopy(self.c['lines'][0])
        other['line_id'] = 'L99'
        self.c['lines'].append(other)
        d = r006_details(self.c)
        self.assertTrue(any(f.startswith('R006:DUPLICATE:0,2:') for f in d['facts']))
        self.assertEqual(sorted(d['line_ids']), ['L1', 'L99'])

    def test_separate_modifier_is_not_duplicate(self):
        other = copy.deepcopy(self.c['lines'][0])
        other['line_id'] = 'L99'
        other['modifier'] = 'EDU-SEPARATE'
        self.c['lines'].append(other)
        d = r006_details(self.c)
        self.assertEqual(d['facts'], ['R006:OK'])

    def test_missing_service_code_is_unknown(self):
        self.c['lines'][0]['service_code'] = None
        d = r006_details(self.c)
        self.assertEqual(d['facts'], ['R006:UNKNOWN'])


class BuildBlobTests(unittest.TestCase):
    def test_blob_contains_all_three_rules_and_ends_with_newline(self):
        c = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']
        blob = build_blob(c)
        self.assertIn('R001:OK', blob)
        self.assertIn('R003:OK', blob)
        self.assertIn('R006:OK', blob)
        self.assertTrue(blob.endswith('\n'))


if __name__ == '__main__':
    unittest.main()
