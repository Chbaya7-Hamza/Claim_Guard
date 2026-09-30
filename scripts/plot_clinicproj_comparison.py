"""Draw the ClaimGuard vs. clinicProj comparison charts from
scripts/score_clinicproj_comparison.py's verdict.json.

    python scripts/plot_clinicproj_comparison.py

Style matches scripts/plot_model_comparison.py: matplotlib, Agg backend,
the project's established palette.
"""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VERDICT = ROOT / 'outputs' / 'architecture_comparison' / 'gemma3-4b-ollama' / 'verdict.json'
DEFAULT_OUT_DIR = ROOT / 'docs' / 'figures'

GREEN = '#1a9641'   # ClaimGuard
AMBER = '#e8971e'   # clinicProj
INK = '#1c2b3a'


def draw(verdict_path, out_dir, suffix=''):
    verdict = json.loads(Path(verdict_path).read_text(encoding='utf-8'))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    categories = list(verdict['categories'])
    cg_scores = [verdict['categories'][c]['claimguard'] for c in categories]
    cp_scores = [verdict['categories'][c]['clinicproj'] for c in categories]

    fig, ax = plt.subplots(figsize=(9, 5))
    x = range(len(categories))
    width = 0.36
    ax.bar([i - width / 2 for i in x], cg_scores, width, label='ClaimGuard', color=GREEN, zorder=3)
    ax.bar([i + width / 2 for i in x], cp_scores, width, label='clinicProj', color=AMBER, zorder=3)
    ax.set_xticks(list(x))
    ax.set_xticklabels([c.capitalize() for c in categories], rotation=15)
    ax.set_ylabel('Score (0-100)')
    ax.set_ylim(0, 108)
    ax.set_title('Architecture comparison by category')
    ax.legend()
    ax.grid(axis='y', color='#e5e7eb', zorder=0)
    for spine in ('top', 'right'):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_dir / f'architecture_comparison_categories{suffix}.png', dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(4.5, 5))
    systems = ['claimguard', 'clinicproj']
    labels = ['ClaimGuard', 'clinicProj']
    scores = [verdict['overall'][s] for s in systems]
    colors = [GREEN, AMBER]
    bars = ax.bar(labels, scores, color=colors, width=0.55, zorder=3)
    for b, v in zip(bars, scores):
        ax.text(b.get_x() + b.get_width() / 2, v + 2, f'{v:.1f}', ha='center', color=INK, fontweight='bold')
    ax.set_ylim(0, 108)
    ax.set_ylabel('Weighted overall score (0-100)')
    ax.set_title(f"Overall verdict: {verdict['overall']['winner']}")
    ax.grid(axis='y', color='#e5e7eb', zorder=0)
    for spine in ('top', 'right'):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_dir / f'architecture_comparison_overall{suffix}.png', dpi=150)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--verdict', default=str(DEFAULT_VERDICT))
    p.add_argument('--out-dir', default=str(DEFAULT_OUT_DIR))
    p.add_argument('--suffix', default='', help="e.g. '_qwen25-7b' so runs don't overwrite each other's figures")
    a = p.parse_args()
    draw(a.verdict, a.out_dir, a.suffix)
    print(f'Wrote figures to {a.out_dir}')


if __name__ == '__main__':
    main()
