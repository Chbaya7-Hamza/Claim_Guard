import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


class DangerousSinkScanTests(unittest.TestCase):
    def test_finds_eval_in_a_fixture_file(self):
        from security_scan_clinicproj import scan_dangerous_sinks
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'calc.py'
            f.write_text("def calculator(expr):\n    return eval(expr)\n", encoding='utf-8')
            findings = scan_dangerous_sinks(Path(tmp))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]['file'], 'calc.py')
        self.assertIn('eval', findings[0]['line'])

    def test_clean_file_has_no_findings(self):
        from security_scan_clinicproj import scan_dangerous_sinks
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'clean.py'
            f.write_text("def add(a, b):\n    return a + b\n", encoding='utf-8')
            findings = scan_dangerous_sinks(Path(tmp))
        self.assertEqual(findings, [])


class GroundingGuardCheckTests(unittest.TestCase):
    def test_no_grounding_guard_found_when_absent(self):
        from security_scan_clinicproj import has_citation_grounding_guard
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'agent.py'
            f.write_text("def validate_claim(claim, agent):\n    return agent.invoke(claim)\n", encoding='utf-8')
            self.assertFalse(has_citation_grounding_guard(Path(tmp)))

    def test_grounding_guard_found_when_present(self):
        from security_scan_clinicproj import has_citation_grounding_guard
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'agent.py'
            f.write_text("def check_grounding(explanation, finding):\n    pass\n", encoding='utf-8')
            self.assertTrue(has_citation_grounding_guard(Path(tmp)))


if __name__ == '__main__':
    unittest.main()
