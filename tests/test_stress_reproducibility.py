"""Audit and reproducibility (10 points): a judge re-runs the engine and checks it against what was logged.

The status-only accuracy gate cannot notice a change to a result's evidence or wording. The result hash can, so a
change to the engine that alters any result must either be intended (regenerate the sample) or be caught here.
"""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from audit import digest
from audit_log import AuditLog, audited_review
from engine_core import config, load_jsonl
from llm_adapter import MockExplanationProvider
from yara_engine import engine_code_hash, evaluate, pack_hash


class CommittedAuditSampleStillMatchesTheEngine(unittest.TestCase):
    def test_every_logged_result_hash_is_reproduced_by_a_fresh_run(self):
        cfg = config(ROOT)
        logged = {}
        for line in (ROOT / 'outputs/audit_dev/audit.jsonl').read_text(encoding='utf-8').split('\n'):
            if line.strip():
                e = json.loads(line)['event']
                if e.get('event_type') == 'rule_check':
                    logged[(e['claim_id'], e['rule_id'])] = e['result_hash']
        self.assertEqual(len(logged), 6000)
        mismatched = []
        for c in load_jsonl(ROOT / 'data/development/claims.jsonl'):
            for r in evaluate(c, cfg):
                if logged[(r['claim_id'], r['rule_id'])] != digest(r):
                    mismatched.append((r['claim_id'], r['rule_id']))
        self.assertEqual(mismatched, [], 'the engine now produces different result content than the committed audit sample: '
                                         'regenerate outputs/audit_dev if this is intended')


class TraceIdentifiesTheCodeThatRan(unittest.TestCase):
    def test_engine_code_hash_is_stable_and_distinct_from_the_pack_hash(self):
        self.assertEqual(engine_code_hash(), engine_code_hash())
        self.assertEqual(len(engine_code_hash()), 64)
        self.assertNotEqual(engine_code_hash(), pack_hash())

    def test_a_run_records_both_hashes_in_the_audit_log(self):
        import tempfile
        cfg = config(ROOT)
        claim = load_jsonl(ROOT / 'data/development/claims.jsonl')[0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.jsonl'
            _, _, trace = audited_review(AuditLog(path), copy.deepcopy(claim), cfg, provider=MockExplanationProvider())
            events = [json.loads(l)['event'] for l in path.read_text(encoding='utf-8').split('\n') if l.strip()]
        finished = next(e for e in events if e['event_type'] == 'run_finished')
        self.assertEqual(finished['rule_pack_hash'], pack_hash())
        self.assertEqual(finished['engine_code_hash'], engine_code_hash())
        self.assertEqual(trace['engine_code_hash'], engine_code_hash())


if __name__ == '__main__':
    unittest.main()
