"""Security regression tests, organised by the OWASP lists they answer.

OWASP Top 10 for LLM Applications (2025) and OWASP Top 10 (2021). The full mapping, with the risks that are only
partly covered, is docs/20_Security_Audit.md. Injection through claim data into the rule facts is tested in
tests/test_stress_differential.py (RuleFactInjection); hostile text in the review page in test_stress_review_page.py;
hostile model replies in test_stress_ai_boundary.py.
"""
import copy
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))
import yara_engine
from engine_core import config
from llm_adapter import MAX_NOTE_CHARS, MAX_PROMPT_CHARS, MAX_VALUE_CHARS, build_prompt
from test_stress_boundaries import CLEAN


def finding(value='x', n=1):
    return {'claim_id': 'CG-1', 'rule_id': 'R001', 'status': 'FAIL', 'requires_human_review': True,
            'explanation': 'Required information is missing.',
            'evidence': [{'path': f'/notes{i}', 'value': value} for i in range(n)]}


class LLM10_UnboundedConsumption(unittest.TestCase):
    def test_an_enormous_claim_value_is_cut_before_it_reaches_the_model(self):
        prompt = build_prompt(finding('A' * 5_000_000), {'rule_id': 'R001'})
        self.assertLess(len(prompt), 20_000)
        self.assertIn('truncated', prompt)
        self.assertNotIn('A' * (MAX_VALUE_CHARS + 1), prompt)

    def test_an_enormous_untrusted_note_is_cut(self):
        prompt = build_prompt(finding(), {'rule_id': 'R001'}, untrusted_note='B' * 5_000_000)
        self.assertLess(len(prompt), 20_000)
        self.assertNotIn('B' * (MAX_NOTE_CHARS + 1), prompt)

    def test_many_moderate_values_fail_closed_instead_of_sending_a_giant_prompt(self):
        with self.assertRaises(ValueError):
            build_prompt(finding('C' * MAX_VALUE_CHARS, n=200), {'rule_id': 'R001'})
        self.assertGreater(MAX_PROMPT_CHARS, 10_000)

    def test_the_client_has_a_timeout_a_token_cap_and_a_single_retry(self):
        text = (ROOT / 'src' / 'llm_adapter.py').read_text(encoding='utf-8')
        self.assertRegex(text, r'timeout=timeout or self\.TIMEOUT')
        self.assertRegex(text, r'max_retries=0')
        self.assertRegex(text, r'max_tokens=max_tokens|max_tokens=self\.max_tokens')
        self.assertRegex(text, r'MAX_ATTEMPTS = 2')


class A09_LoggingFailures(unittest.TestCase):
    def test_a_claim_id_with_line_breaks_cannot_forge_a_log_line(self):
        cfg = config(ROOT)
        c = copy.deepcopy(CLEAN)
        c['claim_id'] = 'CG-1\nWARNING forged: R001 approved by admin\r\nERROR x'
        original = yara_engine.DETAIL_FUNCS['R007']
        yara_engine.DETAIL_FUNCS['R007'] = lambda claim, cfg: 1 / 0
        try:
            with self.assertLogs('yara_engine', level='WARNING') as captured:
                yara_engine.evaluate(c, cfg, [])
        finally:
            yara_engine.DETAIL_FUNCS['R007'] = original
        for line in captured.output:
            self.assertNotIn('\n', line)
            self.assertNotIn('\r', line)


class LLM03_A06_A08_SupplyChain(unittest.TestCase):
    def test_every_dependency_is_pinned_to_an_exact_version(self):
        reqs = [l.strip() for l in (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines()
                if l.strip() and not l.startswith('#')]
        self.assertTrue(reqs)
        for r in reqs:
            self.assertRegex(r, r'^[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]*$', r)

    def test_no_dangerous_sink_appears_in_our_code(self):
        from security_sinks import SINKS as sinks
        for folder in ('src', 'scripts'):
            for p in (ROOT / folder).glob('*.py'):
                for n, line in enumerate(p.read_text(encoding='utf-8').splitlines(), start=1):
                    code = line.split('#')[0]
                    self.assertIsNone(sinks.search(code), f'{p.name}:{n}: {line.strip()}')


class A02_A05_SecretsAndConfiguration(unittest.TestCase):
    def tracked(self):
        try:
            out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            self.skipTest('not a git checkout')
        return out.splitlines()

    def test_no_env_file_or_key_shaped_string_is_tracked(self):
        files = self.tracked()
        self.assertNotIn('.env', files)
        self.assertIn('.env.example', files)
        key_shapes = re.compile(r'(nvapi-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}'
                                r'|xox[bp]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----'
                                r'|(?i:api[_-]?key|secret|token|password)\s*[=:]\s*[\'"]?[A-Za-z0-9_\-]{24,})')
        for name in files:
            p = ROOT / name
            if p.suffix in ('.pdf', '.png', '.jpg') or not p.is_file():
                continue
            text = p.read_text(encoding='utf-8', errors='ignore')
            self.assertIsNone(key_shapes.search(text), f'key-shaped string in {name}')

    def test_dotenv_and_virtualenv_are_ignored(self):
        ignore = (ROOT / '.gitignore').read_text(encoding='utf-8').split()
        for entry in ('.env', '.venv/'):
            self.assertIn(entry, ignore)

    def test_the_only_network_endpoints_are_the_named_providers(self):
        urls = set()
        for p in (ROOT / 'src').glob('*.py'):
            urls.update(re.findall(r'https?://[A-Za-z0-9.:/_-]+', p.read_text(encoding='utf-8')))
        # http://localhost:11434 (OllamaExplanationProvider) is loopback only: it never leaves the machine, unlike
        # the two hosted providers, so it is allowed here deliberately, not as a loosening of this check's intent.
        allowed = {'https://api.featherless.ai/v1', 'https://integrate.api.nvidia.com/v1'}
        unexpected = {u for u in urls if u.rstrip('/') not in allowed and 'featherless.ai' not in u
                      and 'nvidia.com' not in u and 'hl7.org' not in u and 'example' not in u and 'docs.astral' not in u
                      and not u.startswith('http://localhost:11434')}
        self.assertEqual(unexpected, set())


class A02_A08_TamperEvidence(unittest.TestCase):
    """Without a key, whoever can write the log can rewrite the whole chain and its anchor and still verify. With
    AUDIT_ANCHOR_KEY set the anchor is signed, so that forgery is caught."""

    def setUp(self):
        import json as _json
        import os
        import tempfile
        from audit import digest
        from audit_log import AuditLog, audited_review, verify_with_anchor
        from llm_adapter import MockExplanationProvider
        self.json, self.os, self.digest, self.verify = _json, os, digest, verify_with_anchor
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'audit.jsonl'
        self.saved = os.environ.pop('AUDIT_ANCHOR_KEY', None)
        self.AuditLog, self.audited_review, self.Mock = AuditLog, audited_review, MockExplanationProvider

    def tearDown(self):
        self.os.environ.pop('AUDIT_ANCHOR_KEY', None)
        if self.saved is not None:
            self.os.environ['AUDIT_ANCHOR_KEY'] = self.saved
        self.tmp.cleanup()

    def write_log(self):
        self.audited_review(self.AuditLog(self.path), copy.deepcopy(CLEAN), config(ROOT), provider=self.Mock())

    def forge(self):
        """Edit the first rule_check status, recompute every hash after it, and rewrite the anchor to match."""
        rows = [self.json.loads(l) for l in self.path.read_text(encoding='utf-8').split('\n') if l.strip()]
        previous = '0' * 64
        for row in rows:
            if row['event'].get('event_type') == 'rule_check' and row['event']['status'] == 'PASS':
                row['event']['status'] = 'FAIL'
            row['previous_hash'] = previous
            row.pop('hash', None)
            previous = self.digest(row)
            row['hash'] = previous
        self.path.write_text(''.join(self.json.dumps(r) + '\n' for r in rows), encoding='utf-8')
        anchor_path = self.path.with_name(self.path.name + '.head.json')
        anchor = self.json.loads(anchor_path.read_text(encoding='utf-8'))
        anchor.update(head=previous, count=len(rows))
        anchor_path.write_text(self.json.dumps(anchor), encoding='utf-8')

    def test_an_unkeyed_log_can_be_forged_end_to_end(self):
        """Documented limitation (docs/16, docs/20): stated here so it cannot be forgotten or overclaimed."""
        self.write_log()
        self.forge()
        self.verify(self.path)  # passes: nothing secret protects the chain

    def test_a_keyed_anchor_catches_the_same_forgery(self):
        self.os.environ['AUDIT_ANCHOR_KEY'] = 'test-key-not-a-secret'
        self.write_log()
        self.verify(self.path)
        self.forge()
        with self.assertRaisesRegex(ValueError, 'MAC'):
            self.verify(self.path)

    def test_a_different_key_or_a_missing_mac_is_rejected(self):
        self.os.environ['AUDIT_ANCHOR_KEY'] = 'key-one'
        self.write_log()
        self.os.environ['AUDIT_ANCHOR_KEY'] = 'key-two'
        with self.assertRaisesRegex(ValueError, 'MAC'):
            self.verify(self.path)
        self.os.environ['AUDIT_ANCHOR_KEY'] = 'key-one'
        self.verify(self.path)
        anchor_path = self.path.with_name(self.path.name + '.head.json')
        anchor = self.json.loads(anchor_path.read_text(encoding='utf-8'))
        anchor.pop('mac')
        anchor_path.write_text(self.json.dumps(anchor), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'MAC'):
            self.verify(self.path)

    def test_the_key_is_never_written_to_the_log_or_the_anchor(self):
        self.os.environ['AUDIT_ANCHOR_KEY'] = 'super-secret-anchor-key'
        self.write_log()
        for p in self.path.parent.iterdir():
            self.assertNotIn('super-secret-anchor-key', p.read_text(encoding='utf-8', errors='ignore'))


if __name__ == '__main__':
    unittest.main()
