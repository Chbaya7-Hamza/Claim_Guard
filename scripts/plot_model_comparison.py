"""Draw the local-vs-hosted AI-explanation model comparison chart for docs/21 / SPECS.md section 6a.

    python scripts/plot_model_comparison.py        # writes docs/figures/model_comparison.png

Numbers are the pooled results (25 supplied + 11 injection variants, 36 cases) already recorded in
SPECS.md section 6a: gemma3:4b, medgemma-4b-it and Mistral-Nemo-Instruct-2407 each have a real live rate
and latency; qwen3:4b does not get a bar, because it does not have one -- three separate runs (max_tokens
500 / 3000 / 8000) each found cases that failed differently (empty content, a schema-shape rejection, a
90s timeout), so there is no single configuration to report a number for. Drawing a bar at a guessed
height would misrepresent that finding.
"""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / 'docs' / 'figures'

GREEN = '#1a9641'   # gemma3:4b -- winner
BLUE = '#2c7fb8'    # medgemma-4b-it -- viable, slower
AMBER = '#e8971e'   # Mistral-Nemo -- hosted baseline, paid
GRAY = '#9099a8'    # qwen3:4b -- disqualified, no stable config
INK = '#1c2b3a'

MODELS = ['gemma3:4b', 'medgemma-4b-it', 'Mistral-Nemo\n(hosted, paid)', 'qwen3:4b']
COLORS = [GREEN, BLUE, AMBER, GRAY]
LIVE_RATE = [97.2, 83.3, 94.4, None]        # % of 36 cases
MEDIAN_LATENCY = [3.02, 12.88, 4.09, None]  # seconds


def bar_panel(ax, values, colors, title, ylabel, value_fmt, na_label):
    xs = range(len(MODELS))
    heights = [v if v is not None else 0 for v in values]
    bars = ax.bar(xs, heights, color=colors, width=0.62, zorder=3)
    for i, (b, v) in enumerate(zip(bars, values)):
        if v is None:
            b.set_hatch('////')
            b.set_edgecolor('#6b7280')
            b.set_linewidth(1.1)
            ax.text(i, max(h for h in heights if h) * 0.06, na_label, ha='center', va='bottom',
                    fontsize=8.5, color='#4b5563', rotation=90)
        else:
            ax.text(i, v + max(heights) * 0.015, value_fmt(v), ha='center', va='bottom',
                    fontsize=10.5, fontweight='bold', color=INK)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(MODELS, fontsize=9.2)
    ax.set_ylabel(ylabel, fontsize=9.5, color='#4b5563')
    ax.set_title(title, fontsize=11.5, color=INK, fontweight='bold', pad=10)
    ax.spines[['top', 'right']].set_visible(False)
    ax.spines[['left', 'bottom']].set_color('#d1d5db')
    ax.tick_params(colors='#4b5563')
    ax.set_ylim(0, max(heights) * 1.28)
    ax.grid(axis='y', color='#e5e7eb', linewidth=0.8, zorder=0)


def main():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 5))
    bar_panel(ax1, LIVE_RATE, COLORS, 'Live answer rate', '% of 36 cases',
              lambda v: f'{v:.1f}%', 'no stable\nconfig found')
    bar_panel(ax2, MEDIAN_LATENCY, COLORS, 'Median latency (live answers)', 'seconds',
              lambda v: f'{v:.1f}s', 'unbounded\n(3s–90s+)')

    handles = [plt.Rectangle((0, 0), 1, 1, color=GREEN), plt.Rectangle((0, 0), 1, 1, color=BLUE),
               plt.Rectangle((0, 0), 1, 1, color=AMBER),
               plt.Rectangle((0, 0), 1, 1, facecolor='white', edgecolor='#6b7280', hatch='////')]
    labels = ['gemma3:4b — winner: fastest, most reliable, free, 84-case stress track record',
              'medgemma-4b-it — viable: safe, but ~4x slower and less reliable',
              'Mistral-Nemo — hosted baseline (chosen before this comparison), paid per call',
              'qwen3:4b — disqualified: no max_tokens value worked across all 36 cases']
    fig.legend(handles, labels, loc='lower center', ncol=1, frameon=False, fontsize=9.3,
               bbox_to_anchor=(0.5, -0.16))
    fig.suptitle('AI-explanation model comparison — same 36 cases, same scorer, same prompt (v1.6.0 + closing gate)',
                 fontsize=12.5, color=INK, fontweight='bold', y=1.02)
    fig.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / 'model_comparison.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'Wrote {FIG / "model_comparison.png"}')


if __name__ == '__main__':
    main()
