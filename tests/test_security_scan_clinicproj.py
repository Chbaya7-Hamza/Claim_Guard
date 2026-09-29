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


class ScanDirectoriesTests(unittest.TestCase):
    def test_merges_findings_across_several_directories(self):
        # ClaimGuard's own code spans src/ and scripts/, unlike clinicProj's
        # single-directory adapted copy -- _scan_directories() is how both
        # get scored by the same measurement instead of one being hardcoded.
        from security_scan_clinicproj import _scan_directories
        with tempfile.TemporaryDirectory() as tmp:
            d1, d2 = Path(tmp) / 'src', Path(tmp) / 'scripts'
            d1.mkdir()
            d2.mkdir()
            (d1 / 'a.py').write_text("def f():\n    return eval('1')\n", encoding='utf-8')
            (d2 / 'b.py').write_text("def check_grounding(x):\n    pass\n", encoding='utf-8')
            result = _scan_directories([d1, d2])
        self.assertEqual(len(result['dangerous_sinks']), 1)
        self.assertEqual(result['dangerous_sinks'][0]['file'], 'a.py')
        self.assertTrue(result['has_citation_grounding'])  # found in d2, even though d1 has none

    def test_clean_directories_have_no_findings_and_no_grounding(self):
        from security_scan_clinicproj import _scan_directories
        with tempfile.TemporaryDirectory() as tmp:
            d1, d2 = Path(tmp) / 'src', Path(tmp) / 'scripts'
            d1.mkdir()
            d2.mkdir()
            (d1 / 'a.py').write_text("def add(a, b):\n    return a + b\n", encoding='utf-8')
            result = _scan_directories([d1, d2])
        self.assertEqual(result, {'dangerous_sinks': [], 'has_citation_grounding': False})


if __name__ == '__main__':
    unittest.main()
