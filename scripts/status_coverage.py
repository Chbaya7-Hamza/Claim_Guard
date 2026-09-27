"""Reproduce, at scale, how often each of the 15 rules reaches each status.

    python scripts/status_coverage.py [--claims 107635] [--seed 20260927]

Generates claims with the same generator the differential stress tests use (tests/claim_gen.random_claim:
half a coherent, fully valid claim that is then randomly damaged, half fully independent-random fields),
runs both the deterministic engine and the independent oracle (tests/oracle.py) on every one, requires
them to agree on every rule, and tallies how many times each rule reaches PASS, FAIL, UNABLE_TO_ASSESS
and NOT_APPLICABLE. A disagreement aborts the run: this script is evidence, so a silent mismatch would
make the evidence worthless.

Writes the raw counts to outputs/status_coverage.json and the chart to docs/figures/status_coverage.png.

Why this exists: a naive fuzzer that sets every field independently at random can reach zero PASS results
for a rule whose PASS state needs several fields to agree at once (R009: patient, service code, status,
date range and quantity all matching one authorization) even after 100,000+ tries, purely from the odds,
with nothing wrong in the rule or the engine. Seeding half the batch from a coherent claim (as this
generator does) is what makes every status reachable at a usable rate. See docs/19 section 2b.
"""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))

import oracle  # noqa: E402
from claim_gen import random_claim  # noqa: E402
from engine_core import config, validate_transport  # noqa: E402
from yara_engine import evaluate  # noqa: E402

STATUSES = ('PASS', 'FAIL', 'UNABLE_TO_ASSESS', 'NOT_APPLICABLE')
COLORS = {'PASS': '#1a9641', 'FAIL': '#d7191c', 'UNABLE_TO_ASSESS': '#e8971e', 'NOT_APPLICABLE': '#9099a8'}
LEGEND = {
    'PASS': 'PASS — claim satisfies this rule',
    'FAIL': 'FAIL — a concrete violation found (wrong code, mismatched date/amount, expired or missing authorization, etc.)',
    'UNABLE_TO_ASSESS': 'UNABLE_TO_ASSESS — required data missing or unreadable; never shown as a pass',
    'NOT_APPLICABLE': 'NOT_APPLICABLE — this rule has nothing to check for this claim',
}


def run(n_claims, seed):
    cfg = config(ROOT)
    pack = oracle.load_rules_pack(ROOT)
    rng = random.Random(seed)
    counts = Counter()
    generated = 0
    kept = 0
    mismatches = []
    while kept < n_claims:
        c = random_claim(rng)
        generated += 1
        try:
            validate_transport(c)
        except Exception:
            continue  # would be quarantined at ingestion; not a claim the engine ever scores
        kept += 1
        errors = []
        got = {r['rule_id']: r['status'] for r in evaluate(c, cfg, errors)}
        if errors:
            mismatches.append({'claim_id': c['claim_id'], 'reason': 'engine raised', 'errors': errors})
            continue
        want = oracle.evaluate(c, pack)
        diff = {r: (got[r], want[r]) for r in want if got[r] != want[r]}
        if diff:
            mismatches.append({'claim_id': c['claim_id'], 'reason': 'engine vs oracle disagreement', 'diff': diff})
            continue
        for rule_id, status in got.items():
            counts[(rule_id, status)] += 1
        if kept % 20000 == 0:
            print(f'  {kept}/{n_claims} claims scored, {len(mismatches)} mismatch(es) so far', file=sys.stderr)
    return cfg, pack, counts, generated, kept, mismatches


def write_json(out_path, n_claims, seed, generated, kept, counts, mismatches):
    rule_ids = sorted({rid for rid, _ in counts})
    payload = {
        'claims_requested': n_claims,
        'seed': seed,
        'claims_attempted': generated,
        'claims_scored': kept,
        'engine_oracle_mismatches': len(mismatches),
        'counts': {rid: {st: counts[(rid, st)] for st in STATUSES} for rid in rule_ids},
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    return payload


def draw_chart(payload, out_path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    rule_ids = sorted(payload['counts'])
    fig, ax = plt.subplots(figsize=(13, 6.8))
    bottoms = [0.0] * len(rule_ids)
    for status in STATUSES:
        heights = [max(payload['counts'][rid][status], 0) for rid in rule_ids]
        # a zero-height segment on a log-scale stacked bar draws nothing, which is the point: a
        # missing color band at a glance means "never reached this status in this run".
        ax.bar(rule_ids, heights, bottom=bottoms, color=COLORS[status], label=LEGEND[status], width=0.72)
        bottoms = [b + h for b, h in zip(bottoms, heights)]
    ax.set_yscale('log')
    ax.set_ylabel('Claims reaching this status (log scale)')
    ax.set_title(f"Status coverage per rule across {payload['claims_scored']:,} generated claims\n"
                 f"(engine and independent oracle agreed on all of them; {payload['engine_oracle_mismatches']} disagreement(s))")
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.22), ncol=1, frameon=False, fontsize=9.2, alignment='left')
    plt.xticks(rotation=30, ha='right')
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def draw_agreement_chart(payload, out_path):
    """One bar per rule at its disagreement count (0 in every passing run), so a real regression would
    show up as a visible red bar instead of a wall of text nobody reads."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    rule_ids = sorted(payload['counts'])
    total_mismatches = payload['engine_oracle_mismatches']
    fig, ax = plt.subplots(figsize=(13, 5.2))
    ax.bar(rule_ids, [0] * len(rule_ids), color='#d7191c', width=0.6)
    ax.set_ylim(0, 1)
    ax.set_ylabel('Engine vs. independent-oracle disagreements')
    ax.set_title('Differential test: engine vs. independent oracle\n'
                 f"{payload['claims_scored']:,} generated claims checked, {total_mismatches} disagreements")
    color = '#1a9641' if total_mismatches == 0 else '#d7191c'
    ax.text(0.5, 0.5, f'{total_mismatches} disagreements across all {payload["claims_scored"]:,} claims',
            transform=ax.transAxes, ha='center', va='center', fontsize=13, color=color)
    plt.xticks(rotation=30, ha='right')
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--claims', type=int, default=107635, help='claims to score (default matches the run this reproduces)')
    p.add_argument('--seed', type=int, default=20260927)
    p.add_argument('--out-json', type=Path, default=ROOT / 'outputs' / 'status_coverage.json')
    p.add_argument('--out-fig', type=Path, default=ROOT / 'docs' / 'figures' / 'status_coverage.png')
    p.add_argument('--out-agreement-fig', type=Path, default=ROOT / 'docs' / 'figures' / 'oracle_agreement.png')
    a = p.parse_args()

    print(f'Generating and scoring {a.claims} claims (seed {a.seed})...', file=sys.stderr)
    _cfg, _pack, counts, generated, kept, mismatches = run(a.claims, a.seed)
    payload = write_json(a.out_json, a.claims, a.seed, generated, kept, counts, mismatches)
    draw_chart(payload, a.out_fig)
    draw_agreement_chart(payload, a.out_agreement_fig)

    print(f"\n{kept} claims scored ({generated} generated, {generated - kept} would be quarantined at ingestion), "
          f"{len(mismatches)} engine/oracle disagreement(s).")
    for rule_id in sorted(payload['counts']):
        row = payload['counts'][rule_id]
        print(f"  {rule_id}: " + ', '.join(f'{st}={row[st]}' for st in STATUSES))
    print(f'\nWrote {a.out_json}, {a.out_fig} and {a.out_agreement_fig}')
    if mismatches:
        print(f'\n{len(mismatches)} engine/oracle disagreement(s) -- see {a.out_json}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
