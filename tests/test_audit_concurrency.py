import unittest, sys, json, tempfile, subprocess, threading
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from audit import verify
from audit_log import AuditLog, verify_with_anchor


def event(tag, i):
    return {'event_type': 'system_decision', 'run_id': 'r', 'claim_id': f'{tag}-{i}',
            'decision': 'no_findings_for_review', 'reason': 'x'}


class ConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'audit.jsonl'

    def tearDown(self):
        self.tmp.cleanup()

    def test_three_processes_appending_at_once_keep_one_valid_chain(self):
        procs = [subprocess.Popen([sys.executable, str(ROOT / 'tests/_audit_worker.py'), str(self.path), '100', tag])
                 for tag in 'ABC']
        self.assertEqual([p.wait(timeout=120) for p in procs], [0, 0, 0])
        head, n = verify_with_anchor(self.path)
        self.assertEqual(n, 300)
        rows = [json.loads(l) for l in self.path.read_text().splitlines()]
        self.assertEqual([r['sequence'] for r in rows], list(range(1, 301)))
        # every writer's events are all present and in that writer's own order
        for tag in 'ABC':
            mine = [r['event']['claim_id'] for r in rows if r['event']['claim_id'].startswith(tag)]
            self.assertEqual(mine, [f'{tag}-{i}' for i in range(100)])

    def test_threads_sharing_one_log_object(self):
        log = AuditLog(self.path)

        def work(tag):
            for i in range(60):
                log.append_system_events([event(tag, i)])
        ts = [threading.Thread(target=work, args=(t,)) for t in 'WXYZ']
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(verify_with_anchor(self.path)[1], 240)

    def test_two_instances_alternating_do_not_fork_the_chain(self):
        a, b = AuditLog(self.path), AuditLog(self.path)
        for i in range(20):
            (a if i % 2 == 0 else b).append_system_events([event('alt', i)])
        self.assertEqual(verify_with_anchor(self.path)[1], 20)

    def test_review_decisions_interleave_safely_with_system_events(self):
        a, b = AuditLog(self.path), AuditLog(self.path)
        a.append_system_events([event('s', 0)])
        b.append_review_decisions([dict(claim_id='C', rule_id='R001', action='request_information', actor='t', reason='why')])
        a.append_system_events([event('s', 1)])
        self.assertEqual(verify_with_anchor(self.path)[1], 3)

    def test_a_torn_final_line_is_refused_not_silently_extended(self):
        log = AuditLog(self.path)
        log.append_system_events([event('t', 0), event('t', 1)])
        with open(self.path, 'ab') as f:
            f.write(b'{"sequence": 3, "recorded_at": "x", "previo')  # crash mid-write
        with self.assertRaisesRegex(ValueError, 'torn'):
            log.append_system_events([event('t', 2)])

    def test_a_malformed_anchor_gives_a_clear_error(self):
        log = AuditLog(self.path)
        log.append_system_events([event('m', 0)])
        log.anchor_path.write_text('{"head": ', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'unreadable or malformed'):
            AuditLog(self.path)
        log.anchor_path.write_text('[]', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'unreadable or malformed'):
            verify_with_anchor(self.path)

    def test_anchor_is_replaced_atomically_and_leaves_no_temp_files(self):
        log = AuditLog(self.path)
        for i in range(5):
            log.append_system_events([event('a', i)])
        self.assertEqual([p.name for p in Path(self.tmp.name).glob('*.tmp')], [])
        self.assertEqual(json.loads(log.anchor_path.read_text())['count'], 5)

    def test_a_long_final_row_is_still_found_by_the_tail_reader(self):
        log = AuditLog(self.path)
        big = event('big', 0); big['reason'] = 'x' * 200_000  # larger than the initial tail window
        log.append_system_events([big])
        other = AuditLog.__new__(AuditLog)
        AuditLog.__init__(other, self.path)
        other.append_system_events([event('after', 0)])
        self.assertEqual(verify_with_anchor(self.path)[1], 2)


if __name__ == '__main__':
    unittest.main()
