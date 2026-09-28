"""Run both ClaimGuard and clinicProj over the same claim sample, recording
per-claim latency, status and raw output for scripts/score_clinicproj_comparison.py.

    python scripts/run_clinicproj_comparison.py --sample-size 36

Needs Ollama running locally with gemma3:4b pulled (`ollama serve`) and, for
the clinicproj side, comparison/clinicproj_adapted's own dependencies
installed (see comparison/README.md) -- this module itself stays importable
without those, so its sampling/recording logic can be unit-tested offline.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / 'outputs' / 'architecture_comparison'


def sample_claims(claims_path, sample_size=None):
    sys.path.insert(0, str(ROOT / 'src'))
    from jsonl_reader import parse_json, read_lines
    claims = []
    for n, line, read_error in read_lines(claims_path):
        if read_error:
            continue
        c, parse_error = parse_json(line)
        if parse_error:
            continue
        claims.append(c)
        if sample_size is not None and len(claims) >= sample_size:
            break
    return claims


def run_system(claims, runner, system_name, out_path):
    """runner(claim) -> {'status': str, 'raw_output': str}, or raises. Every
    claim gets exactly one recorded row, success or failure -- a raised
    exception on one claim never stops the batch."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open('w', encoding='utf-8') as f:
        for claim in claims:
            t0 = time.perf_counter()
            row = {'claim_id': claim['claim_id'], 'system': system_name,
                   'latency_s': None, 'status': None, 'raw_output': None, 'error': None}
            try:
                result = runner(claim)
                row['status'] = result['status']
                row['raw_output'] = result['raw_output']
            except Exception as e:  # noqa: BLE001 -- one claim's failure must never abort the batch
                row['error'] = f'{type(e).__name__}: {e}'
            row['latency_s'] = time.perf_counter() - t0
            f.write(json.dumps(row) + '\n')
            print(f"[{system_name}] {claim['claim_id']}: "
                  f"{row['status'] or 'ERROR'} ({row['latency_s']:.1f}s)")


def _claimguard_runner():
    sys.path.insert(0, str(ROOT / 'src'))
    from claim_review import review_package
    from engine_core import config
    from llm_adapter import OllamaExplanationProvider
    cfg = config(ROOT)
    provider = OllamaExplanationProvider()

    def run(claim):
        rule_results, ai_explanations, trace = review_package(claim, cfg, provider=provider)
        if rule_results is None:
            raise ValueError(trace.get('ingestion_error', 'ingestion failed'))
        statuses = {r['status'] for r in rule_results}
        status = 'INVALID' if 'FAIL' in statuses else ('REVIEW_REQUIRED' if 'UNABLE_TO_ASSESS' in statuses else 'VALID')
        return {'status': status, 'raw_output': json.dumps({'rule_results': rule_results, 'ai_explanations': ai_explanations})}

    return run


def _clinicproj_runner():
    adapted = ROOT / 'comparison' / 'clinicproj_adapted'
    sys.path.insert(0, str(adapted))
    from agent import build_agent, build_rag_index, validate_claim
    # build_agent()'s default rag_index uses a relative "policies" path (matching
    # the original script's behavior when run from inside comparison/clinicproj_adapted/)
    # -- this harness runs from the repo root, so the policies dir must be absolute.
    rag_index = build_rag_index(str(adapted / 'policies'))
    agent = build_agent(rag_index=rag_index)

    def run(claim):
        reply = validate_claim(claim, agent)
        try:
            parsed = json.loads(reply)
            status = parsed.get('overall_status')
        except json.JSONDecodeError:
            status = None  # recorded, not fatal -- see Review Focus
        return {'status': status, 'raw_output': reply}

    return run


def _check_ollama_is_serving():
    """One clear upfront message instead of discovering claim-by-claim (see
    the plan's Review Focus: 'the harness must fail loudly ... instead of
    a bare traceback or a silently-empty output file')."""
    import urllib.request
    import urllib.error
    try:
        urllib.request.urlopen('http://localhost:11434/v1/models', timeout=3)
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        raise SystemExit(
            f'Cannot reach Ollama at http://localhost:11434 ({type(e).__name__}: {e}). '
            f'Is Ollama running? Start it with `ollama serve` and confirm gemma3:4b is '
            f'pulled (`ollama pull gemma3:4b`) before rerunning this script.'
        )


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--claims', default=str(ROOT / 'data' / 'development' / 'claims.jsonl'))
    p.add_argument('--sample-size', type=int, default=36)
    p.add_argument('--system', choices=('claimguard', 'clinicproj', 'both'), default='both')
    a = p.parse_args()

    _check_ollama_is_serving()
    claims = sample_claims(a.claims, a.sample_size)
    print(f'{len(claims)} claim(s) sampled from {a.claims}')

    if a.system in ('claimguard', 'both'):
        run_system(claims, _claimguard_runner(), 'claimguard', OUT_DIR / 'claimguard.jsonl')
    if a.system in ('clinicproj', 'both'):
        run_system(claims, _clinicproj_runner(), 'clinicproj', OUT_DIR / 'clinicproj.jsonl')


if __name__ == '__main__':
    main()
