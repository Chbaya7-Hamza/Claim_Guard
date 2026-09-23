import unittest, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import yara_x


class YaraPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = yara_x.compile((ROOT / 'rules' / 'core.yar').read_text(encoding='utf-8'))

    def outcomes(self, blob):
        scan = self.rules.scan(blob.encode('utf-8'))
        by_rule = {}
        for rule in scan.matching_rules:
            meta = dict(rule.metadata)
            by_rule.setdefault(meta['rule_id'], set()).add(meta['outcome'])
        return by_rule

    def test_r001_fail(self):
        self.assertEqual(self.outcomes('R001:MISSING:/invoice_number\n')['R001'], {'FAIL'})

    def test_r001_pass(self):
        self.assertEqual(self.outcomes('R001:OK\n')['R001'], {'PASS'})

    def test_r003_fail_inactive(self):
        self.assertEqual(self.outcomes('R003:INACTIVE:status=cancelled\n')['R003'], {'FAIL'})

    def test_r003_fail_out_of_period(self):
        blob = 'R003:OUT_OF_PERIOD:/lines/0/service_date:service=2026-01-01:start=2026-02-01:end=2026-03-01\n'
        self.assertEqual(self.outcomes(blob)['R003'], {'FAIL'})

    def test_r003_unable(self):
        self.assertEqual(self.outcomes('R003:UNKNOWN\n')['R003'], {'UNABLE_TO_ASSESS'})

    def test_r003_pass(self):
        self.assertEqual(self.outcomes('R003:OK\n')['R003'], {'PASS'})

    def test_r006_fail(self):
        self.assertEqual(self.outcomes('R006:DUPLICATE:0,2:key=SVC-LAB|2026-05-25|\n')['R006'], {'FAIL'})

    def test_r006_unable(self):
        self.assertEqual(self.outcomes('R006:UNKNOWN\n')['R006'], {'UNABLE_TO_ASSESS'})

    def test_r006_pass(self):
        self.assertEqual(self.outcomes('R006:OK\n')['R006'], {'PASS'})

    def test_rule_versions_match_rules_json(self):
        import json
        rules_json = {r['rule_id']: r for r in json.loads((ROOT / 'rules/rules.json').read_text())}
        scan = self.rules.scan(
            b'R001:OK\nR003:OK\nR006:OK\n'
        )
        for rule in scan.matching_rules:
            meta = dict(rule.metadata)
            self.assertEqual(meta['rule_version'], rules_json[meta['rule_id']]['version'])


if __name__ == '__main__':
    unittest.main()
