"""Turn scripts/run_clinicproj_comparison.py's and
scripts/security_scan_clinicproj.py's recorded output into a weighted,
rerunnable verdict -- the benchmark that says who actually wins, and why.

    python scripts/score_clinicproj_comparison.py

Pure stdlib: reads JSONL/JSON, does no live model calls, so this script and
its tests never need Ollama or clinicProj's dependencies installed.
"""
import argparse
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / 'outputs' / 'architecture_comparison'

# See docs/superpowers/specs/2026-09-28-clinicproj-architecture-comparison-design.md
# "Who wins benchmark scoring" for the rationale behind these weights.
WEIGHTS = {'correctness': 30, 'security': 20, 'deliverability': 20, 'rapidness': 15, 'efficiency': 15}

STATUS_ALIASES = {'INCOMPLETE': 'REVIEW_REQUIRED'}  # clinicProj's 4th status folds into ClaimGuard's 3


def derive_claim_status(rule_rows: list) -> str:
    """From a list of {'status': ...} rows (ClaimGuard's 15-per-claim shape,
    or the answer key's), the same claim-level status vocabulary both
    systems get compared on: VALID / REVIEW_REQUIRED / INVALID."""
    statuses = {r['status'] for r in rule_rows}
    if 'FAIL' in statuses:
        return 'INVALID'
    if 'UNABLE_TO_ASSESS' in statuses:
        return 'REVIEW_REQUIRED'
    return 'VALID'


def correctness_score(gold: dict, predicted: dict) -> float:
    """gold/predicted: {claim_id: status}. Missing predictions count as
    wrong (a claim the harness recorded an error for is not a free pass)."""
    normalized_pred = {cid: STATUS_ALIASES.get(s, s) for cid, s in predicted.items()}
    correct = sum(1 for cid, gold_status in gold.items() if normalized_pred.get(cid) == gold_status)
    return 100.0 * correct / len(gold) if gold else 0.0


def rapidness_scores(latencies: dict) -> dict:
    """latencies: {system: [seconds, ...]} of SUCCESSFUL runs only -- the
    caller filters out errored rows before building this dict (a system
    that fails fast is not fast, it just failed). The faster system's
    median scores 100; the other is scored proportionally (half the speed
    = half the score). A system with no successful runs scores 0, not a
    crash -- and every input key always gets an output entry so
    weighted_verdict() never KeyErrors looking one up."""
    medians = {sys: statistics.median(vals) for sys, vals in latencies.items() if vals}
    fastest = min(medians.values()) if medians else None
    return {sys: (round(100.0 * fastest / medians[sys], 4) if sys in medians else 0.0) for sys in latencies}


def efficiency_score(dependency_counts: dict) -> dict:
    """A simple, documented proxy: fewer third-party runtime dependencies
    scores higher. Normalized the same way as rapidness_scores -- ratio to
    the leanest system, not "1 - ratio to the heaviest" (that older formula
    always scored the heavier system exactly 0 no matter how close it
    actually was, and scored a tie 0 for both). Not a token-cost measure --
    see docs/24 for why (neither system's provider reliably reports tokens
    for every call in this setup)."""
    fewest = min(dependency_counts.values())
    return {sys: (round(100.0 * fewest / count, 2) if count else 100.0) for sys, count in dependency_counts.items()}


def _system_security_score(report: dict) -> float:
    score = 100.0
    score -= 25.0 if report.get('dangerous_sinks') else 0.0
    score -= 25.0 if not report.get('has_citation_grounding') else 0.0
    if report.get('injection_probe_applicable', True):
        probe = report.get('injection_resistance')
        # "Not verified" (no probe ever run, a probe that errored, or a reply that
        # wasn't even parseable) is not evidence of resistance -- it must not score
        # the same as a probe that actually ran, parsed, and resisted. All three
        # deduct the same -15.
        if probe is None or probe.get('error') or probe.get('parseable') is False:
            score -= 15.0
        elif probe.get('injected_claim_incorrectly_marked_valid'):
            score -= 30.0  # the coarse status itself was flipped -- the worse failure
        elif probe.get('genuine_finding_suppressed'):
            score -= 20.0  # status held, but the specific finding still got dropped
    return max(score, 0.0)


def security_score(security_report: dict) -> dict:
    """security_report holds a peer sub-report per system -- both are scored by
    the same formula, from real scan data. A system whose sub-report sets
    injection_probe_applicable=False (ClaimGuard's rule-engine-plus-explanation
    architecture has no free-text conversational surface to probe the way
    clinicProj's agent does) skips that one deduction tier rather than being
    penalized for a dimension that doesn't apply to it -- its injection
    resistance is covered by its own existing test suite instead."""
    return {
        'claimguard': _system_security_score(security_report.get('claimguard', {})),
        'clinicproj': _system_security_score(security_report.get('clinicproj', {})),
    }


def deliverability_score(checklist: dict) -> dict:
    """checklist: {system: {item: bool}}. Each present item is worth an
    equal share of 100."""
    scores = {}
    for system, items in checklist.items():
        scores[system] = round(100.0 * sum(1 for v in items.values() if v) / len(items), 2) if items else 0.0
    return scores


def weighted_verdict(category_scores: dict) -> dict:
    categories = {}
    for cat, scores in category_scores.items():
        winner = max(scores, key=scores.get)
        if len(set(scores.values())) == 1:
            winner = 'tie'
        categories[cat] = {**scores, 'winner': winner}

    systems = {s for scores in category_scores.values() for s in scores}
    overall = {s: round(sum(WEIGHTS[c] * category_scores[c][s] for c in WEIGHTS) / 100, 2) for s in systems}
    overall_winner = max(overall, key=overall.get)
    if len(set(overall.values())) == 1:
        overall_winner = 'tie'

    return {'categories': categories, 'overall': {**overall, 'winner': overall_winner}}


def _load_jsonl(path):
    return [json.loads(l) for l in Path(path).read_text(encoding='utf-8').splitlines() if l.strip()]


def _count_requirements(path):
    """Non-comment, non-blank lines in a requirements.txt -- counted from the
    real file rather than hand-tallied, so this number can't silently drift
    out of sync with the file it's supposed to describe."""
    return sum(1 for l in Path(path).read_text(encoding='utf-8').splitlines()
               if l.strip() and not l.strip().startswith('#'))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--claims', default=str(ROOT / 'data' / 'development' / 'claims.jsonl'))
    p.add_argument('--gold', default=str(ROOT / 'data' / 'development' / 'expected_results.jsonl'))
    p.add_argument('--output', default=str(OUT_DIR / 'verdict.json'))
    a = p.parse_args()

    claimguard_rows = _load_jsonl(OUT_DIR / 'claimguard.jsonl')
    clinicproj_rows = _load_jsonl(OUT_DIR / 'clinicproj.jsonl')
    gold_rows = _load_jsonl(a.gold)
    security_report = json.loads((OUT_DIR / 'security_report.json').read_text(encoding='utf-8'))

    gold_by_claim = {}
    for r in gold_rows:
        gold_by_claim.setdefault(r['claim_id'], []).append(r)
    gold_status = {cid: derive_claim_status(rows) for cid, rows in gold_by_claim.items()}
    sampled_ids = {r['claim_id'] for r in claimguard_rows} & set(gold_status)

    claimguard_status = {r['claim_id']: r['status'] for r in claimguard_rows if r['status']}
    clinicproj_status = {r['claim_id']: r['status'] for r in clinicproj_rows if r['status']}
    gold_sampled = {cid: gold_status[cid] for cid in sampled_ids}

    category_scores = {
        'correctness': {
            'claimguard': correctness_score(gold_sampled, claimguard_status),
            'clinicproj': correctness_score(gold_sampled, clinicproj_status),
        },
        'rapidness': rapidness_scores({
            # error is None: a claim that failed didn't get answered quickly, it just
            # didn't get answered -- its near-zero latency must not count as speed.
            'claimguard': [r['latency_s'] for r in claimguard_rows if r['latency_s'] is not None and r['error'] is None],
            'clinicproj': [r['latency_s'] for r in clinicproj_rows if r['latency_s'] is not None and r['error'] is None],
        }),
        'security': security_score(security_report),
        'deliverability': deliverability_score({
            # auth_rbac_designed: False for both -- no RBAC implementation or design
            # doc exists in this repo (the mobile-app RBAC discussion lives only in
            # session memory/specs, not committed here); claiming it True with zero
            # in-repo evidence would be exactly the kind of typed-in, unverifiable
            # figure this whole benchmark exists to avoid.
            'claimguard': {'audit_log': True, 'test_suite': True, 'ci': True, 'auth_rbac_designed': False,
                           'offline_capable': True, 'schema_validated_output': True},
            'clinicproj': {'audit_log': False, 'test_suite': False, 'ci': False, 'auth_rbac_designed': False,
                           'offline_capable': True, 'schema_validated_output': False},
        }),
        'efficiency': efficiency_score(dependency_counts={
            'claimguard': _count_requirements(ROOT / 'requirements.txt'),
            'clinicproj': _count_requirements(ROOT / 'comparison' / 'clinicproj_adapted' / 'requirements.txt'),
        }),
    }

    verdict = weighted_verdict(category_scores)
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.output).write_text(json.dumps(verdict, indent=2), encoding='utf-8')
    print(json.dumps(verdict, indent=2))


if __name__ == '__main__':
    main()
