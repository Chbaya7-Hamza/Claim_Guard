"""Benchmark the YARA-X rule engine against a plain-Python implementation of the same 15 rules.

    python scripts/benchmark_yara_vs_python.py [--claims 20000] [--seed 20260927]

The Python side is not a toy rewrite for this script: it is `tests/oracle.py`, the same independent,
from-scratch reimplementation that has already been checked to reproduce the answer key on all 9,000 public
results and to agree with the engine on 107,635+ generated claims (`scripts/status_coverage.py`). Using it here
means the "Python" side of this benchmark is held to the same correctness bar as the real engine, not a
strawman.

Times both on the same generated claims (`tests/claim_gen.py`) and reports throughput, plus a maintainability
comparison (lines of rule-definition code) and the safety argument (a YARA-X rule is a declarative pattern
match with no side effects; a Python rule function is an arbitrary function that could do anything).
"""
import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))

import oracle  # noqa: E402
from claim_gen import random_claim  # noqa: E402
from engine_core import config, validate_transport  # noqa: E402
from yara_engine import evaluate as yara_evaluate  # noqa: E402


def generate_claims(n, seed):
    rng = random.Random(seed)
    claims = []
    while len(claims) < n:
        c = random_claim(rng)
        try:
            validate_transport(c)
        except Exception:
            continue
        claims.append(c)
    return claims


def time_it(label, fn, claims, *extra):
    t0 = time.perf_counter()
    for c in claims:
        fn(c, *extra)
    elapsed = time.perf_counter() - t0
    per_claim_ms = (elapsed / len(claims)) * 1000
    print(f'{label}: {elapsed:.2f}s total, {per_claim_ms:.3f} ms/claim, {len(claims) / elapsed:,.0f} claims/s')
    return elapsed


def line_count(path):
    return len((ROOT / path).read_text(encoding='utf-8').splitlines())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--claims', type=int, default=20000)
    p.add_argument('--seed', type=int, default=20260927)
    a = p.parse_args()

    print(f'Generating {a.claims} claims (seed {a.seed})...')
    claims = generate_claims(a.claims, a.seed)

    cfg = config(ROOT)
    pack = oracle.load_rules_pack(ROOT)

    print('\n--- Warm-up (JIT/cache effects, not measured) ---')
    for c in claims[:50]:
        yara_evaluate(c, cfg)
        oracle.evaluate(c, pack)

    print('\n--- Timed runs ---')
    yara_s = time_it('YARA-X engine   ', yara_evaluate, claims, cfg)
    python_s = time_it('Python (oracle) ', oracle.evaluate, claims, pack)

    ratio = python_s / yara_s if yara_s else float('inf')
    print(f'\nYARA-X is {ratio:.2f}x the speed of the plain-Python oracle on this run.' if ratio >= 1
          else f'\nThe plain-Python oracle is {1 / ratio:.2f}x the speed of YARA-X on this run.')

    print('\n--- Maintainability: lines of rule-definition code ---')
    print(f'  rules/core.yar (compiled YARA-X rule pack):     {line_count("rules/core.yar")} lines')
    print(f'  rules/rules.json (rule metadata/catalogue):     {line_count("rules/rules.json")} lines')
    print(f'  tests/oracle.py (independent Python reimpl.):   {line_count("tests/oracle.py")} lines')
    print('  (oracle.py also has to reimplement fact extraction from raw claim JSON; core.yar matches against')
    print('   the same pre-extracted, typed facts src/facts_extractor.py already produces for the real engine.)')

    print('\n--- Why YARA-X, not just a Python if/else chain (qualitative) ---')
    print('  - A YARA-X rule is a declarative pattern match: it can only match or not match. It cannot open a file,')
    print('    make a network call, mutate shared state, or raise an unbounded/infinite loop. A Python rule function')
    print('    is an arbitrary function -- nothing stops a bug (or a future contributor) from giving it a side effect.')
    print('  - Rules are text, reviewable and diffable one rule at a time (`rules/core.yar`), independent of the')
    print('    surrounding orchestration code -- closer to how the fictional rulebook itself reads.')
    print('  - The compiled pack has one version (`rule_version`) auditors can cite per rule; a Python function')
    print('    change is only visible as a diff against the whole file.')


if __name__ == '__main__':
    main()
