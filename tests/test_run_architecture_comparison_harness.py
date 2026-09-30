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
        from run_architecture_comparison import sample_claims
        claims = sample_claims(ROOT / 'data' / 'development' / 'claims.jsonl', sample_size=5)
        self.assertEqual(len(claims), 5)
        self.assertEqual(len({c['claim_id'] for c in claims}), 5)


class RunSystemTests(unittest.TestCase):
    def test_records_one_row_per_claim_with_latency_and_status(self):
        from run_architecture_comparison import run_system

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
        from run_architecture_comparison import run_system

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

    def test_a_parse_error_from_the_runner_is_carried_through_to_the_row(self):
        # Distinguishes "not valid JSON at all" from "valid JSON missing the
        # key" (both score as a miss, but only the first is a parse_error) --
        # see parse_architecture_b_reply.
        from run_architecture_comparison import run_system

        def runner(claim):
            return {'status': None, 'raw_output': 'not json', 'parse_error': 'Expecting value: line 1 column 1'}

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / 'system.jsonl'
            run_system([{'claim_id': 'CG-1'}], runner, system_name='fake', out_path=out_path)
            rows = [json.loads(l) for l in out_path.read_text(encoding='utf-8').splitlines()]

        self.assertEqual(rows[0]['parse_error'], 'Expecting value: line 1 column 1')

    def test_no_parse_error_key_defaults_to_none_not_a_missing_key(self):
        from run_architecture_comparison import run_system

        def runner(claim):
            return {'status': 'VALID', 'raw_output': '{}'}  # no parse_error key at all

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / 'system.jsonl'
            run_system([{'claim_id': 'CG-1'}], runner, system_name='fake', out_path=out_path)
            rows = [json.loads(l) for l in out_path.read_text(encoding='utf-8').splitlines()]

        self.assertIn('parse_error', rows[0])
        self.assertIsNone(rows[0]['parse_error'])


class ParseArchitectureBReplyTests(unittest.TestCase):
    def test_invalid_json_sets_parse_error(self):
        from run_architecture_comparison import parse_architecture_b_reply
        result = parse_architecture_b_reply('not json at all')
        self.assertIsNone(result['status'])
        self.assertIsNotNone(result['parse_error'])

    def test_valid_json_missing_the_key_has_no_parse_error(self):
        # Distinct from the invalid-JSON case: the agent replied with a real
        # JSON object, it just didn't include overall_status.
        from run_architecture_comparison import parse_architecture_b_reply
        result = parse_architecture_b_reply('{"findings": []}')
        self.assertIsNone(result['status'])
        self.assertIsNone(result['parse_error'])

    def test_valid_reply_extracts_the_status(self):
        from run_architecture_comparison import parse_architecture_b_reply
        result = parse_architecture_b_reply('{"overall_status": "VALID"}')
        self.assertEqual(result['status'], 'VALID')
        self.assertIsNone(result['parse_error'])


if __name__ == '__main__':
    unittest.main()
