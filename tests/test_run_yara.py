import unittest, sys, json, tempfile, copy, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from engine_core import config, load_jsonl
from evaluate import index
from run_yara import run


class RunYaraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config(ROOT)
        cls.claims = load_jsonl(ROOT / 'data/development/claims.jsonl')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, lines):
        p = self.dir / 'in.jsonl'
        p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return p

    def results(self):
        return [json.loads(l) for l in (self.dir / 'out.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]

    def test_clean_input_yields_15_results_per_claim_and_no_problems(self):
        p = self.write([json.dumps(c) for c in self.claims[:5]])
        s = run(p, self.dir / 'out.jsonl', self.cfg)
        self.assertEqual((s['claims'], s['results']), (5, 75))
        self.assertEqual((s['fail_closed_claims'], s['unreadable_lines'], s['tool_errors']), ([], [], []))

    def test_one_bad_claim_never_aborts_the_batch(self):
        good = self.claims[0]
        broken = copy.deepcopy(self.claims[1]); del broken['lines']
        p = self.write([json.dumps(good), '{not json', json.dumps(broken), json.dumps(self.claims[2]), '{"no_id": 1}'])
        s = run(p, self.dir / 'out.jsonl', self.cfg)
        out = self.results()
        self.assertEqual(s['claims'], 4)
        self.assertEqual(len(out), 3 * 15)  # good, broken (fail-closed), good; unidentifiable ones cannot carry results
        self.assertEqual([x['claim_id'] for x in s['fail_closed_claims']], [broken['claim_id']])
        self.assertEqual(len(s['unreadable_lines']), 2)
        closed = [r for r in out if r['claim_id'] == broken['claim_id']]
        self.assertEqual(len(closed), 15)
        self.assertEqual({r['status'] for r in closed}, {'UNABLE_TO_ASSESS'})
        self.assertTrue(all(r['requires_human_review'] and r['corrective_action'] for r in closed))

    def test_output_is_accepted_by_the_strict_scorer_even_with_a_fail_closed_claim(self):
        broken = copy.deepcopy(self.claims[1]); broken['currency'] = ''
        p = self.write([json.dumps(self.claims[0]), json.dumps(broken)])
        run(p, self.dir / 'out.jsonl', self.cfg)
        # fail-closed evidence is /claim_id, so it resolves against the original claim
        claims = {c['claim_id']: c for c in (self.claims[0], broken)}
        index(self.results(), claims)

    def test_cli_exit_code_is_2_when_anything_was_degraded_and_0_otherwise(self):
        py = sys.executable
        ok = self.write([json.dumps(self.claims[0])])
        r = subprocess.run([py, str(ROOT / 'src/run_yara.py'), '--input', str(ok), '--output', str(self.dir / 'o1.jsonl')],
                           capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stderr)
        bad = self.write([json.dumps(self.claims[0]), '{oops'])
        r = subprocess.run([py, str(ROOT / 'src/run_yara.py'), '--input', str(bad), '--output', str(self.dir / 'o2.jsonl')],
                           capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 2)
        self.assertIn('unreadable', r.stderr)
        self.assertEqual(len((self.dir / 'o2.jsonl').read_text().splitlines()), 15)  # the good claim was still processed

    def test_limit_is_respected(self):
        p = self.write([json.dumps(c) for c in self.claims[:10]])
        self.assertEqual(run(p, self.dir / 'out.jsonl', self.cfg, limit=3)['claims'], 3)


if __name__ == '__main__':
    unittest.main()
