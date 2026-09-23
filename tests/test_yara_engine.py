import unittest, sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config
from yara_engine import evaluate, EngineError


class YaraEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config(ROOT)
        cls.example = json.loads((ROOT / 'examples/worked_cases.json').read_text())[0]['claim']

    def setUp(self):
        self.c = copy.deepcopy(self.example)

    def result(self, rid):
        return next(r for r in evaluate(self.c, self.cfg) if r['rule_id'] == rid)

    def test_clean_claim_all_pass(self):
        for rid in ('R001', 'R003', 'R006'):
            self.assertEqual(self.result(rid)['status'], 'PASS')

    def test_r001_missing_fails(self):
        self.c['invoice_number'] = None
        r = self.result('R001')
        self.assertEqual(r['status'], 'FAIL')
        self.assertEqual(r['confidence'], None)
        self.assertEqual(r['confidence_kind'], 'not_probabilistic')
        self.assertEqual(r['method'], 'deterministic')

    def test_r003_boundary_passes(self):
        day = self.c['lines'][0]['service_date']
        self.c['coverage']['start_date'] = day
        self.c['coverage']['end_date'] = day
        self.assertEqual(self.result('R003')['status'], 'PASS')

    def test_r003_unknown_coverage_is_not_pass(self):
        self.c['coverage']['end_date'] = None
        self.assertEqual(self.result('R003')['status'], 'UNABLE_TO_ASSESS')

    def test_r003_known_failure_dominates_unknown(self):
        self.c['coverage']['end_date'] = None
        self.c['coverage']['status'] = 'cancelled'
        self.assertEqual(self.result('R003')['status'], 'FAIL')

    def test_r006_duplicate_and_modifier(self):
        other = copy.deepcopy(self.c['lines'][0])
        other['line_id'] = 'L99'
        self.c['lines'].append(other)
        self.assertEqual(self.result('R006')['status'], 'FAIL')
        other['modifier'] = 'EDU-SEPARATE'
        self.assertEqual(self.result('R006')['status'], 'PASS')

    def test_missing_rule_in_pack_raises(self):
        cfg = {
            **self.cfg,
            'rules': [r for r in self.cfg['rules'] if r['rule_id'] != 'R001'] + [
                {**next(r for r in self.cfg['rules'] if r['rule_id'] == 'R001'), 'rule_id': 'R999', 'version': '1.0.0'}
            ],
        }
        # R999 has no facts and no YARA rule at all -> must raise, never silently pass.
        import yara_engine
        yara_engine.DETAIL_FUNCS['R999'] = yara_engine.DETAIL_FUNCS.pop('R001')
        try:
            with self.assertRaises(EngineError):
                evaluate(self.c, cfg)
        finally:
            yara_engine.DETAIL_FUNCS['R001'] = yara_engine.DETAIL_FUNCS.pop('R999')


if __name__ == '__main__':
    unittest.main()
