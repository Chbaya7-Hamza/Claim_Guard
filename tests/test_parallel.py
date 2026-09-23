import unittest, sys, json, copy, tempfile, threading, time
from pathlib import Path
from unittest.mock import MagicMock
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config, load_jsonl
from audit_log import AuditLog, audited_review, audited_review_many, verify_ai_ordering, verify_with_anchor
from llm_adapter import FeatherlessExplanationProvider, MockExplanationProvider
from yara_engine import evaluate

GOOD = json.dumps({'explanation': 'The unit price on L1 is missing.', 'cited_evidence_paths': ['/lines/0/unit_price'],
                   'cited_rule_ids': ['R001'], 'needs_human_review': True})


class SlowMock(MockExplanationProvider):
    """Template answers, but each call takes `delay` seconds (stands in for network latency)."""
    def __init__(self, delay):
        self.delay = delay
        self.calls = 0
        self._lock = threading.Lock()

    def explain(self, finding, rule, untrusted_note=None):
        time.sleep(self.delay)
        with self._lock:
            self.calls += 1
        return super().explain(finding, rule, untrusted_note)


class ThreadSafetyTests(unittest.TestCase):
    FINDING = {'claim_id': 'C', 'rule_id': 'R001', 'requires_human_review': True,
               'evidence': [{'path': '/lines/0/unit_price', 'value': None}]}

    def test_provider_call_metadata_is_per_thread(self):
        """Two threads are inside explain() at the same moment on ONE provider object; each must
        read back its own token usage and attempt count, never the other thread's."""
        p = FeatherlessExplanationProvider(api_key='k')
        barrier = threading.Barrier(2)
        tokens_for_thread = {'tA': 111, 'tB': 222}

        def create(**kw):
            barrier.wait(timeout=10)  # both threads are mid-call together
            time.sleep(0.05)
            c = MagicMock()
            c.choices = [MagicMock(message=MagicMock(content=GOOD))]
            c.usage = MagicMock(prompt_tokens=1, completion_tokens=1,
                                total_tokens=tokens_for_thread[threading.current_thread().name])
            return c

        p.client.chat.completions.create = create
        seen = {}

        def run(name):
            p.explain(self.FINDING, {'rule_id': 'R001'})
            seen[name] = (p.last_usage['total_tokens'], p.last_attempts)

        ts = [threading.Thread(target=run, args=(n,), name=n) for n in tokens_for_thread]
        [t.start() for t in ts]
        [t.join(timeout=20) for t in ts]
        self.assertEqual(seen, {'tA': (111, 1), 'tB': (222, 1)})
        self.assertIsNone(p.last_usage)  # the main thread never made a call


class ParallelReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config(ROOT)
        cls.claims = load_jsonl(ROOT / 'data/development/claims.jsonl')[:40]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def items(self, claims):
        return [{'claim': copy.deepcopy(c)} for c in claims]

    def test_parallel_results_equal_sequential_results(self):
        seq_log = AuditLog(Path(self.tmp.name) / 'seq.jsonl')
        par_log = AuditLog(Path(self.tmp.name) / 'par.jsonl')
        seq = [audited_review(seq_log, copy.deepcopy(c), self.cfg, provider=MockExplanationProvider()) for c in self.claims]
        par = audited_review_many(par_log, self.items(self.claims), self.cfg, provider=MockExplanationProvider(), workers=6)
        self.assertEqual([r[0] for r in seq], [r[0] for r in par])  # identical rule results, in input order
        self.assertEqual([[a['output'] for a in r[1]] for r in seq], [[a['output'] for a in r[1]] for r in par])

    def test_parallel_log_is_one_valid_ordered_chain(self):
        log = AuditLog(Path(self.tmp.name) / 'par.jsonl')
        audited_review_many(log, self.items(self.claims), self.cfg, provider=MockExplanationProvider(), workers=8)
        head, n = verify_with_anchor(log.path)
        stats = verify_ai_ordering(log.path)
        self.assertGreater(stats['ai_requests'], 5)
        self.assertEqual(stats['ai_requests'], stats['ai_recommendations'])
        self.assertEqual(stats['unanswered_requests'], 0)
        rows = [json.loads(l) for l in log.path.read_text().splitlines()]
        self.assertEqual([r['sequence'] for r in rows], list(range(1, n + 1)))
        runs = {r['event']['run_id'] for r in rows if r['event'].get('event_type') == 'run_started'}
        self.assertEqual(len(runs), len(self.claims))

    def test_write_ahead_holds_under_concurrency(self):
        """When ANY model call starts, its own ai_request is already durable in the log."""
        log = AuditLog(Path(self.tmp.name) / 'wa.jsonl')
        violations = []

        class Spy(MockExplanationProvider):
            def explain(spy, finding, rule, untrusted_note=None):
                events = [json.loads(l)['event'] for l in log.path.read_text().splitlines() if l.strip()]
                mine = [e for e in events if e.get('event_type') == 'ai_request'
                        and e['claim_id'] == finding['claim_id'] and e['rule_id'] == finding['rule_id']]
                if len(mine) != 1:
                    violations.append((finding['claim_id'], finding['rule_id'], len(mine)))
                time.sleep(0.01)
                return super().explain(finding, rule, untrusted_note)

        audited_review_many(log, self.items(self.claims[:20]), self.cfg, provider=Spy(), workers=6)
        self.assertEqual(violations, [])

    def test_parallelism_actually_shortens_wall_time(self):
        claims = [c for c in self.claims if any(r['status'] in ('FAIL', 'UNABLE_TO_ASSESS')
                                                for r in evaluate(c, self.cfg))][:12]
        self.assertGreaterEqual(len(claims), 8)
        delay = 0.08
        t = time.monotonic()
        audited_review_many(AuditLog(Path(self.tmp.name) / 'a.jsonl'), self.items(claims), self.cfg,
                            provider=SlowMock(delay), workers=1)
        sequential = time.monotonic() - t
        t = time.monotonic()
        audited_review_many(AuditLog(Path(self.tmp.name) / 'b.jsonl'), self.items(claims), self.cfg,
                            provider=SlowMock(delay), workers=6)
        parallel = time.monotonic() - t
        self.assertLess(parallel, sequential * 0.6, (sequential, parallel))

    def test_a_failing_claim_is_not_silent(self):
        class FailingLog(AuditLog):
            def append_system_events(self, events):
                if any(e['event_type'] == 'ai_request' and e['claim_id'] == self.poison for e in events):
                    raise OSError('disk full')
                return super().append_system_events(events)

        log = FailingLog(Path(self.tmp.name) / 'f.jsonl')
        claims = [c for c in self.claims if any(r['status'] in ('FAIL', 'UNABLE_TO_ASSESS') for r in evaluate(c, self.cfg))]
        log.poison = claims[3]['claim_id']
        provider = SlowMock(0)
        with self.assertRaises(OSError):
            audited_review_many(log, self.items(claims[:8]), self.cfg, provider=provider, workers=4)
        # the poisoned claim's model call never happened (write-ahead), even though others ran
        events = [json.loads(l)['event'] for l in log.path.read_text().splitlines()]
        self.assertFalse(any(e.get('event_type') == 'ai_recommendation' and e['claim_id'] == log.poison for e in events))


if __name__ == '__main__':
    unittest.main()
