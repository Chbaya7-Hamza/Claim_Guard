import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src'))


class SampleClaimsTests(unittest.TestCase):
    def test_sample_size_caps_the_number_of_claims_read(self):
        from run_clinicproj_comparison import sample_claims
        claims = sample_claims(ROOT / 'data' / 'development' / 'claims.jsonl', sample_size=5)
        self.assertEqual(len(claims), 5)
        self.assertEqual(len({c['claim_id'] for c in claims}), 5)


class RunSystemTests(unittest.TestCase):
    def test_records_one_row_per_claim_with_latency_and_status(self):
        from run_clinicproj_comparison import run_system

        claims = [{'claim_id': 'CG-1'}, {'claim_id': 'CG-2'}]

        def fake_runner(claim):
            return {'status': 'VALID', 'raw_output': '{}'}

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / 'system.jsonl'
            run_system(claims, fake_runner, system_name='fake', out_path=out_path)
            rows = [json.loads(l) for l in out_path.read_text(encoding='utf-8').splitlines()]

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['claim_id'], 'CG-1')
        self.assertEqual(rows[0]['system'], 'fake')
        self.assertEqual(rows[0]['status'], 'VALID')
        self.assertIsInstance(rows[0]['latency_s'], float)
        self.assertIsNone(rows[0]['error'])

    def test_a_claim_that_raises_is_recorded_not_fatal(self):
        from run_clinicproj_comparison import run_system

        claims = [{'claim_id': 'CG-1'}, {'claim_id': 'CG-2'}]

        def flaky_runner(claim):
            if claim['claim_id'] == 'CG-1':
                raise ConnectionError('Ollama not running')
            return {'status': 'VALID', 'raw_output': '{}'}

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / 'system.jsonl'
            run_system(claims, flaky_runner, system_name='fake', out_path=out_path)
            rows = [json.loads(l) for l in out_path.read_text(encoding='utf-8').splitlines()]

        self.assertEqual(len(rows), 2)
        self.assertIn('Ollama not running', rows[0]['error'])
        self.assertIsNone(rows[0]['status'])
        self.assertIsNone(rows[1]['error'])


if __name__ == '__main__':
    unittest.main()
