"""Put a real number on audit-log concurrency, beyond the existing 3-process / 300-event test
(tests/test_audit_concurrency.py) -- docs/19 flags "concurrency beyond the existing 3-process audit
test" as not covered. This runs many more real OS processes writing many more events, verifies the
chain is still exactly one valid sequence afterward, and reports throughput.

    python scripts/benchmark_audit_concurrency.py [--processes 20] [--events-per-process 500]
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from audit_log import verify_with_anchor  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--processes', type=int, default=20)
    p.add_argument('--events-per-process', type=int, default=500)
    a = p.parse_args()

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'audit.jsonl'
        tags = [f'P{i:02d}' for i in range(a.processes)]
        t0 = time.perf_counter()
        procs = [subprocess.Popen([sys.executable, str(ROOT / 'tests/_audit_worker.py'), str(path),
                                    str(a.events_per_process), tag]) for tag in tags]
        codes = [proc.wait(timeout=300) for proc in procs]
        elapsed = time.perf_counter() - t0

        total_expected = a.processes * a.events_per_process
        if any(c != 0 for c in codes):
            print(f'FAILED: {sum(1 for c in codes if c != 0)} of {a.processes} worker processes exited non-zero')
            return 1

        head, n = verify_with_anchor(path)
        rows = [l for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]
        import json
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
