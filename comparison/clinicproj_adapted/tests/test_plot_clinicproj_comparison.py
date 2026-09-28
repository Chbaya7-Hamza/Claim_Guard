import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))

FIXTURE_VERDICT = {
    "categories": {
        "correctness": {"claimguard": 92.0, "clinicproj": 61.0, "winner": "claimguard"},
        "security": {"claimguard": 100.0, "clinicproj": 40.0, "winner": "claimguard"},
        "deliverability": {"claimguard": 100.0, "clinicproj": 16.67, "winner": "claimguard"},
        "rapidness": {"claimguard": 100.0, "clinicproj": 22.0, "winner": "claimguard"},
        "efficiency": {"claimguard": 78.57, "clinicproj": 0.0, "winner": "claimguard"},
    },
    "overall": {"claimguard": 92.99, "clinicproj": 39.5, "winner": "claimguard"},
}


class PlotComparisonTests(unittest.TestCase):
    def test_draws_both_figures_from_a_verdict_file(self):
        from plot_clinicproj_comparison import draw
        with tempfile.TemporaryDirectory() as tmp:
            verdict_path = Path(tmp) / 'verdict.json'
            verdict_path.write_text(json.dumps(FIXTURE_VERDICT), encoding='utf-8')
            out_dir = Path(tmp) / 'figures'
            draw(verdict_path, out_dir)
            categories_png = out_dir / 'architecture_comparison_categories.png'
            overall_png = out_dir / 'architecture_comparison_overall.png'
            self.assertTrue(categories_png.exists())
            self.assertTrue(overall_png.exists())
            self.assertGreater(categories_png.stat().st_size, 1000)
            self.assertGreater(overall_png.stat().st_size, 1000)


if __name__ == '__main__':
    unittest.main()
