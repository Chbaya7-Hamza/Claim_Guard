"""Helper process for test_audit_concurrency: appends N events to a shared log."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from audit_log import AuditLog

path, n, tag = sys.argv[1], int(sys.argv[2]), sys.argv[3]
log = AuditLog(path)
for i in range(n):
    log.append_system_events([{'event_type': 'system_decision', 'run_id': 'r', 'claim_id': f'{tag}-{i}',
                               'decision': 'no_findings_for_review', 'reason': 'x'}])
