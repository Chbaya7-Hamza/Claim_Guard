"""Put a real number on audit-log concurrency, beyond the existing 3-process / 300-event test
(tests/test_audit_concurrency.py) -- docs/19 flags "concurrency beyond the existing 3-process audit
test" as not covered. This runs many more real OS processes writing many more events, verifies the
chain is still exactly one valid sequence afterward, and reports throughput.

    python scripts/benchmark_audit_concurrency.py [--processes 20] [--events-per-process 500]
"""
import argparse
import json
import multiprocessing
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from audit_log import AuditLog, verify_with_anchor  # noqa: E402


def _worker(path, n, tag):
    log = AuditLog(path)
    for i in range(n):
        log.append_system_events([{'event_type': 'system_decision', 'run_id': 'r', 'claim_id': f'{tag}-{i}',
                                   'decision': 'no_findings_for_review', 'reason': 'x'}])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--processes', type=int, default=20)
    p.add_argument('--events-per-process', type=int, default=500)
    a = p.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'audit.jsonl'
        tags = [f'P{i:02d}' for i in range(a.processes)]
        t0 = time.perf_counter()
        # multiprocessing.Process, not subprocess: real separate OS processes (same file-locking
        # behavior we're measuring), spawned from a picklable module-level target instead of a
        # second script file.
        procs = [multiprocessing.Process(target=_worker, args=(str(path), a.events_per_process, tag))
                 for tag in tags]
        for proc in procs:
            proc.start()
        for proc in procs:
            proc.join(timeout=300)
        elapsed = time.perf_counter() - t0
        codes = [proc.exitcode for proc in procs]

        total_expected = a.processes * a.events_per_process
        if any(c != 0 for c in codes):
            print(f'FAILED: {sum(1 for c in codes if c != 0)} of {a.processes} worker processes exited non-zero')
            return 1

        head, n = verify_with_anchor(path)
        rows = [l for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]
        sequences = [json.loads(r)['sequence'] for r in rows]
        ok_sequence = sequences == list(range(1, len(rows) + 1))

        print(f'{a.processes} processes x {a.events_per_process} events = {total_expected} events, '
              f'in {elapsed:.2f}s ({n / elapsed:.0f} events/s)')
        print(f'verify_with_anchor: {n} events, chain {"valid" if n == total_expected else "COUNT MISMATCH"}')
        print(f'sequence numbers exactly 1..{len(rows)}, no gaps or duplicates: {ok_sequence}')

        # every writer's own events, in that writer's own order (no interleaving corruption)
        per_tag_ok = True
        for tag in tags:
            mine = [json.loads(r)['event']['claim_id'] for r in rows if json.loads(r)['event']['claim_id'].startswith(tag)]
            want = [f'{tag}-{i}' for i in range(a.events_per_process)]
            if mine != want:
                per_tag_ok = False
                print(f'  MISMATCH for {tag}: got {len(mine)} events, wanted {len(want)}')
        print(f'every writer\'s own events present, in its own order: {per_tag_ok}')

        ok = n == total_expected and ok_sequence and per_tag_ok
        print('\nRESULT:', 'PASS' if ok else 'FAIL')
        return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
