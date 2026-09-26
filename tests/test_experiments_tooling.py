"""The experiment tooling and the committed experiment data (docs/21). No network, no API key."""
import inspect
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
import analyze_experiments as A
import run_experiments as R
from llm_adapter import FeatherlessExplanationProvider, build_prompt

RAW = ROOT / 'experiments' / 'raw'


class ProductionDefaultsAreUnchanged(unittest.TestCase):
    """Making temperature, top_p and the instruction text parameters must not change what production does."""

    def test_provider_defaults_are_the_frozen_ones(self):
        params = inspect.signature(FeatherlessExplanationProvider.__init__).parameters
        self.assertEqual(params['temperature'].default, 0)
        self.assertEqual(params['top_p'].default, 1)
        self.assertIsNone(params['instructions'].default)
        self.assertEqual(params['max_tokens'].default, 500)
        # Changed on purpose in round two (docs/21): Mistral-Nemo + prompt v1.4.0. The round-one baseline is R.DEFAULT_MODEL.
        self.assertEqual(FeatherlessExplanationProvider.DEFAULT_MODEL, 'mistralai/Mistral-Nemo-Instruct-2407')
        self.assertEqual(R.DEFAULT_MODEL, 'Qwen/Qwen2.5-14B-Instruct')

    def test_the_shipped_prompt_is_v1_4_0_and_is_the_prompt_that_was_measured(self):

        shipped = (ROOT / 'prompts' / 'explain_findings.md').read_text(encoding='utf-8').replace(chr(13) + chr(10), chr(10))

        measured = (ROOT / 'prompts' / 'variants' / 'guided.md').read_text(encoding='utf-8').replace(chr(13) + chr(10), chr(10))

        self.assertTrue(shipped.startswith('# Explanation helper prompt v1.4.0' + chr(10)))

        self.assertEqual(shipped.split(chr(10), 1)[1], measured.split(chr(10), 1)[1])  # only the title line differs

        frozen = (ROOT / 'prompts' / 'variants' / 'v1_3_0.md').read_text(encoding='utf-8')

        self.assertTrue(frozen.startswith('# Explanation helper prompt v1.3.0'))

        self.assertIn('Mistral-Nemo', (ROOT / 'src' / 'llm_adapter.py').read_text(encoding='utf-8'))



    def test_the_default_prompt_is_still_the_frozen_file_and_an_override_replaces_only_the_instructions(self):
        finding = {'claim_id': 'CG-1', 'rule_id': 'R001', 'status': 'FAIL', 'requires_human_review': True,
                   'explanation': 'x', 'evidence': [{'path': '/a', 'value': 1}]}
        default = build_prompt(finding, {'rule_id': 'R001'})
        self.assertTrue(default.startswith((ROOT / 'prompts' / 'explain_findings.md').read_text(encoding='utf-8')))
        variant = build_prompt(finding, {'rule_id': 'R001'}, None, 'OVERRIDDEN INSTRUCTIONS')
        self.assertTrue(variant.startswith('OVERRIDDEN INSTRUCTIONS'))
        self.assertEqual(variant.split('OVERRIDDEN INSTRUCTIONS', 1)[1], default.split(default.split(chr(10) + '## Required output schema')[0], 1)[1])

    def test_the_prompt_variants_exist_and_keep_the_safety_sentences(self):
        for name, path in R.PROMPTS.items():
            text = path.read_text(encoding='utf-8') if path else (ROOT / 'prompts' / 'explain_findings.md').read_text(encoding='utf-8')
            self.assertIn('untrusted', text.lower(), name)
            self.assertIn('needs_human_review', text, name)


class Statistics(unittest.TestCase):
    def test_wilson_interval(self):
        p, lo, hi = A.wilson(50, 100)
        self.assertAlmostEqual(p, 0.5)
        self.assertAlmostEqual(lo, 0.4038, places=3)
        self.assertAlmostEqual(hi, 0.5962, places=3)
        self.assertAlmostEqual(A.wilson(100, 100)[1], 0.963, places=3)
        self.assertEqual(A.wilson(0, 0), (0.0, 0.0, 0.0))

    def test_errors_are_classified_so_rate_limiting_cannot_look_like_a_bad_temperature(self):
        self.assertEqual(R.classify('RateLimitError: Error code: 429'), 'transport')
        self.assertEqual(R.classify('APITimeoutError: Request timed out.'), 'transport')
        self.assertEqual(R.classify('PermissionDeniedError: 403 gated'), 'config')
        self.assertEqual(R.classify("ValueError: Ungrounded statement (currency symbol)"), 'model')
        self.assertEqual(R.classify('JSONDecodeError: Expecting value'), 'model')

    def test_garbled_reply_detector(self):
        self.assertTrue(A.is_degenerate('fine ' + chr(0x6570) + chr(0x4e0b)))
        self.assertTrue(A.is_degenerate('{' + '!' * 30))
        self.assertTrue(A.is_degenerate('the ' * 12))
        self.assertFalse(A.is_degenerate('The provider is not listed for policy EDU-PLUS.'))


class CommittedData(unittest.TestCase):
    def setUp(self):
        if not (RAW / 'e1.jsonl').exists():
            self.skipTest('no committed experiment data')

    def records(self):
        for path in sorted(RAW.glob('e*.jsonl')):
            for line in path.read_text(encoding='utf-8').split(chr(10)):
                if line.strip():
                    yield path.stem, json.loads(line)

    def test_every_file_starts_with_a_manifest_that_names_the_commit_and_the_engine(self):
        for path in sorted(RAW.glob('e*.jsonl')):
            first = json.loads(path.read_text(encoding='utf-8').split(chr(10))[0])
            self.assertEqual(first['type'], 'manifest', path.name)
            self.assertRegex(first['commit'], '^[0-9a-f]{40}$')
            self.assertRegex(first['engine_code_hash'], '^[0-9a-f]{64}$')

    def test_no_verdict_was_ever_changed_by_a_setting(self):
        summary = json.loads((ROOT / 'experiments' / 'summary.json').read_text(encoding='utf-8'))
        inv = summary['invariant_verdicts_unchanged']
        calls = sum(1 for _, r in self.records() if r['type'] == 'call')
        self.assertTrue(inv['holds'])
        self.assertEqual(inv['calls_checked'], calls)
        self.assertGreaterEqual(calls, 2000)

    def test_the_results_tables_have_a_row_for_every_configuration(self):
        summary = json.loads((ROOT / 'experiments' / 'summary.json').read_text(encoding='utf-8'))
        tables = (ROOT / 'experiments' / 'results_tables.md').read_text(encoding='utf-8')
        for exp in ('e1', 'e2', 'e3', 'e4', 'e5', 'e6', 'e7', 'e8'):
            for cfg in summary[exp]['configs']:
                self.assertIn('| ' + cfg['label'] + ' |', tables, cfg['cfg_id'])

    def test_every_documented_figure_exists(self):
        doc = (ROOT / 'docs' / '21_Experiments.md').read_text(encoding='utf-8')
        import re
        for name in re.findall(r'\(figures/([a-z0-9_]+\.png)\)', doc):
            self.assertTrue((ROOT / 'docs' / 'figures' / name).exists(), name)

    def test_the_raw_data_holds_no_secret(self):
        env = ROOT / '.env'
        secrets = []
        if env.exists():
            for line in env.read_text(encoding='utf-8', errors='ignore').split(chr(10)):
                if '=' in line and not line.startswith('#'):
                    value = line.split('=', 1)[1].strip()
                    if len(value) >= 12:
                        secrets.append(value)
        for path in list(RAW.glob('*')) + [ROOT / 'experiments' / 'summary.json']:
            text = path.read_text(encoding='utf-8', errors='ignore')
            for secret in secrets:
                self.assertNotIn(secret, text, path.name)
            self.assertNotIn('Bearer ', text, path.name)

    def test_the_grounding_guard_and_the_recorded_calls_use_the_same_case_files(self):
        cases = {c['case_id'] for c in R.load_cases('tuning')} | {c['case_id'] for c in R.load_cases('fresh')} | {c['case_id'] for c in R.load_cases('fresh2')}
        for _, r in self.records():
            if r['type'] == 'call':
                self.assertIn(r['case_id'], cases)


if __name__ == '__main__':
    unittest.main()
