import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from audit import digest  # noqa: E402
from audit_log import AuditLog, verify_with_anchor  # noqa: E402


def _events(n):
    return [{'event_type': 'rule_check', 'claim_id': f'CG-{i}', 'rule_id': 'R001', 'status': 'PASS'} for i in range(n)]


class StrictAnchorTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / 'audit.jsonl'
        AuditLog(self.path)._write(_events(10))

    def tearDown(self):
        self.dir.cleanup()

    def _append_forged_rows_with_valid_chain(self, n=3):
        rows = [json.loads(l) for l in self.path.read_text(encoding='utf-8').splitlines() if l.strip()]
        for i in range(n):
            row = {'sequence': len(rows) + 1, 'recorded_at': 'x', 'previous_hash': rows[-1]['hash'],
                   'event': {'event_type': 'rule_check', 'claim_id': f'FORGED-{i}', 'rule_id': 'R001', 'status': 'PASS'}}
            rows.append({**row, 'hash': digest(row)})
        self.path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')

    def test_a_quiet_log_passes_strict(self):
        self.assertEqual(verify_with_anchor(self.path, strict=True)[1], 10)

    def test_forged_rows_after_the_anchor_pass_the_default_check_but_fail_strict(self):
        self._append_forged_rows_with_valid_chain(3)
        self.assertEqual(verify_with_anchor(self.path)[1], 13)  # the documented limit of the lower-bound anchor
        with self.assertRaisesRegex(ValueError, '3 unanchored row'):
            verify_with_anchor(self.path, strict=True)

    def test_reopening_a_log_is_not_made_stricter(self):
        # AuditLog.__init__ must keep tolerating a crash between the log write and the anchor write.
        self._append_forged_rows_with_valid_chain(1)
        self.assertEqual(AuditLog(self.path).count, 11)


if __name__ == '__main__':
    unittest.main()
