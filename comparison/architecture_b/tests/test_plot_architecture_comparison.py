import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))

FIXTURE_VERDICT = {
    "categories": {
        "correctness": {"architecture_a": 92.0, "architecture_b": 61.0, "winner": "architecture_a"},
        "security": {"architecture_a": 100.0, "architecture_b": 40.0, "winner": "architecture_a"},
        "deliverability": {"architecture_a": 100.0, "architecture_b": 16.67, "winner": "architecture_a"},
        "rapidness": {"architecture_a": 100.0, "architecture_b": 22.0, "winner": "architecture_a"},
        "efficiency": {"architecture_a": 78.57, "architecture_b": 0.0, "winner": "architecture_a"},
    },
    "overall": {"architecture_a": 92.99, "architecture_b": 39.5, "winner": "architecture_a"},
}


class PlotComparisonTests(unittest.TestCase):
    def test_draws_both_figures_from_a_verdict_file(self):
        from plot_architecture_comparison import draw
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
