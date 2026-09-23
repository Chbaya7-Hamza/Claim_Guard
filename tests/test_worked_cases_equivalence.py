import unittest, sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config
from yara_engine import evaluate


class WorkedCasesEquivalenceTests(unittest.TestCase):
    """examples/worked_cases.json is the handbook's own oracle: 10 cases, all
    15 expected statuses each. yara_engine must reproduce every one exactly,
    including the multi-rule UNABLE_TO_ASSESS case (unknown policy_id)."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = config(ROOT)
        cls.cases = json.loads((ROOT / 'examples/worked_cases.json').read_text())

    def test_all_worked_cases_match_status_exactly(self):
        mismatches = []
        for case in self.cases:
            c = case['claim']
            gold = {g['rule_id']: g['status'] for g in case['expected_results']}
            mine = {r['rule_id']: r['status'] for r in evaluate(c, self.cfg)}
            for rid in gold:
                if gold[rid] != mine[rid]:
                    mismatches.append((case['title'], c['claim_id'], rid, gold[rid], mine[rid]))
        self.assertEqual(mismatches, [], f'{len(mismatches)} worked-case status mismatches: {mismatches}')


if __name__ == '__main__':
    unittest.main()
