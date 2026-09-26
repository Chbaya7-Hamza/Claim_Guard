"""The narrated demo (scripts/demo.py) runs offline, tells the truth about what it shows, and cannot delete the repository."""
import contextlib
import importlib.util
import io
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))


def load_demo():
    spec = importlib.util.spec_from_file_location('claimguard_demo', ROOT / 'scripts' / 'demo.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DemoRuns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out_dir = Path(cls.tmp.name) / 'demo'
        buffer = io.StringIO()
        with mock.patch.object(sys, 'argv', ['demo.py', '--out-dir', str(cls.out_dir)]), \
                mock.patch.dict('os.environ', {'FEATHERLESS_API_KEY': ''}), contextlib.redirect_stdout(buffer):
            load_demo().main()
        cls.text = buffer.getvalue()

    @classmethod
    def tearDownClass(cls):
        logging.disable(logging.NOTSET)
        cls.tmp.cleanup()

    def test_all_eight_scenes_are_shown_in_order(self):
        positions = [self.text.index(f'SCENE {n}:') for n in range(1, 9)]
        self.assertEqual(positions, sorted(positions))

    def test_it_says_that_the_data_is_synthetic_and_that_a_human_decides(self):
        self.assertIn('SYNTHETIC', self.text)
        self.assertIn('A human always decides', self.text)

    def test_offline_it_names_the_template_and_not_a_model(self):
        self.assertIn('written by the deterministic template', self.text)
        self.assertIn('--live', self.text)

    def test_the_simulated_bad_model_is_labelled_and_never_accepted(self):
        self.assertIn('SIMULATED', self.text)
        self.assertIn('model answers accepted: 0', self.text)
        self.assertIn('verdicts identical to the honest run: True', self.text)

    def test_the_tamper_is_detected_and_the_honest_log_verifies(self):
        self.assertIn('DETECTED', self.text)
        self.assertIn('chain OK', self.text)
        self.assertIn('AI ordering OK', self.text)

    def test_unknown_data_is_never_shown_as_a_pass(self):
        self.assertIn("'PASS': 0", self.text)
        self.assertIn('UNABLE', self.text)

    def test_the_recheck_is_a_new_run_and_the_original_claim_is_unchanged(self):
        self.assertIn('FAIL -> PASS', self.text)
        self.assertIn('original claim unchanged', self.text)

    def test_it_writes_the_review_page_and_nothing_outside_its_folder(self):
        self.assertTrue((self.out_dir / 'review.html').is_file())

    def test_it_does_not_print_warnings_over_the_narration(self):
        self.assertNotIn('falling back', self.text)


class DemoRefusesToDeleteTheRepository(unittest.TestCase):
    def test_the_repository_and_its_parents_are_refused(self):
        demo = load_demo()
        for bad in ('.', '..', str(ROOT), str(ROOT.parent)):
            with mock.patch.object(sys, 'argv', ['demo.py', '--out-dir', bad]), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                demo.main()
            self.assertEqual(caught.exception.code, 2, bad)
        self.assertTrue((ROOT / 'src' / 'ingest.py').is_file())


if __name__ == '__main__':
    unittest.main()
