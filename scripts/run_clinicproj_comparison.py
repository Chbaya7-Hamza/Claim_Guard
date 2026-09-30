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
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / 'outputs' / 'architecture_comparison'


def _load_dotenv():
    # tiny .env loader (same contract as src/llm_adapter.py: a real env var always wins)
    f = ROOT / '.env'
    if f.exists():
        for line in f.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line.startswith('export '):
                line = line[len('export '):].lstrip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                    v = v[1:-1]  # KEY="value" must not put the quote marks into the credential
                os.environ.setdefault(k.strip(), v)


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
    """runner(claim) -> {'status': str, 'raw_output': str, 'parse_error': str|None (optional)},
    or raises. Every claim gets exactly one recorded row, success or failure --
    a raised exception on one claim never stops the batch."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open('w', encoding='utf-8') as f:
        for claim in claims:
            t0 = time.perf_counter()
            row = {'claim_id': claim['claim_id'], 'system': system_name, 'lenient_status': None, 'wrapped_json': False,
                   'latency_s': None, 'status': None, 'raw_output': None, 'error': None, 'parse_error': None}
            try:
                result = runner(claim)
                row['status'] = result['status']
                row['raw_output'] = result['raw_output']
                row['parse_error'] = result.get('parse_error')
                row['lenient_status'] = result.get('lenient_status')
                row['wrapped_json'] = result.get('wrapped_json', False)
            except Exception as e:  # noqa: BLE001 -- one claim's failure must never abort the batch
                row['error'] = f'{type(e).__name__}: {e}'
            row['latency_s'] = time.perf_counter() - t0
            f.write(json.dumps(row) + '\n')
            print(f"[{system_name}] {claim['claim_id']}: "
                  f"{row['status'] or 'ERROR'} ({row['latency_s']:.1f}s)")


def _claimguard_runner(provider_name, model):
    sys.path.insert(0, str(ROOT / 'src'))
    from claim_review import review_package
    from engine_core import config
    from llm_adapter import FeatherlessExplanationProvider, OllamaExplanationProvider
    cfg = config(ROOT)
    provider = FeatherlessExplanationProvider(model=model) if provider_name == 'featherless'         else OllamaExplanationProvider()

    def run(claim):
        rule_results, ai_explanations, trace = review_package(claim, cfg, provider=provider)
        if rule_results is None:
            raise ValueError(trace.get('ingestion_error', 'ingestion failed'))
        statuses = {r['status'] for r in rule_results}
        status = 'INVALID' if 'FAIL' in statuses else ('REVIEW_REQUIRED' if 'UNABLE_TO_ASSESS' in statuses else 'VALID')
        return {'status': status, 'raw_output': json.dumps({'rule_results': rule_results, 'ai_explanations': ai_explanations})}

    return run


def extract_json_object(text):
    """The first JSON object embedded in text, or None. Tries every '{' in turn with a real JSON decoder, so prose that
    contains braces before the JSON ('see {below}: ```json {...}```') does not break the extraction the way slicing from the
    first '{' to the last '}' does."""
    decoder = json.JSONDecoder()
    start = text.find('{')
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(text[start:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        start = text.find('{', start + 1)
    return None


def parse_clinicproj_reply(reply: str) -> dict:
    """Pure, independently testable: clinicProj's agent has no schema check
    (unlike ClaimGuard's llm_adapter.py), so its reply can be malformed in two
    different ways a reviewer needs to tell apart -- not valid JSON at all, or
    valid JSON that simply doesn't have an overall_status key. Both count as a
    miss for scoring, but only the first sets parse_error, so the two failure
    modes stay distinguishable in the recorded evidence."""
    try:
        parsed = json.loads(reply)
    except json.JSONDecodeError as e:
        # Disclosed adjustment, recorded beside (never instead of) the strict result: some models wrap a valid JSON object
        # in prose or a code fence. clinicProj has no parser of its own, so strict stays the default score.
        obj = extract_json_object(reply)
        lenient = obj.get('overall_status') if obj else None
        if isinstance(lenient, str):
            lenient = lenient.strip().upper()
        return {'status': None, 'raw_output': reply, 'parse_error': str(e), 'lenient_status': lenient,
                'wrapped_json': lenient is not None}
    return {'status': parsed.get('overall_status'), 'raw_output': reply, 'parse_error': None}


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
        return parse_clinicproj_reply(validate_claim(claim, agent))

    return run


def _check_provider(provider_name):
    if provider_name == 'featherless':
        if not os.environ.get('FEATHERLESS_API_KEY'):
            raise SystemExit('FEATHERLESS_API_KEY is not set (put it in .env or the environment).')
        return
    _check_ollama_is_serving()


def _check_ollama_is_serving():
    """One clear upfront message instead of discovering claim-by-claim (see
    the plan's Review Focus: 'the harness must fail loudly ... instead of
    a bare traceback or a silently-empty output file')."""
    import http.client
    conn = http.client.HTTPConnection('localhost', 11434, timeout=3)
    try:
        conn.request('GET', '/v1/models')
        status = conn.getresponse().status
        if status != 200:
            raise ConnectionError(f'HTTP {status} from the service on port 11434')
    except (ConnectionError, OSError, http.client.HTTPException) as e:
        raise SystemExit(
            f'Cannot reach Ollama at http://localhost:11434 ({type(e).__name__}: {e}). '
            f'Is Ollama running? Start it with `ollama serve` and confirm gemma3:4b is '
            f'pulled (`ollama pull gemma3:4b`) before rerunning this script.'
        )
    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--claims', default=str(ROOT / 'data' / 'development' / 'claims.jsonl'))
    p.add_argument('--sample-size', type=int, default=36)
    p.add_argument('--system', choices=('claimguard', 'clinicproj', 'both'), default='both')
    p.add_argument('--provider', choices=('ollama', 'featherless'), default='ollama')
    p.add_argument('--model', help='required with --provider featherless; both systems run this same model')
    p.add_argument('--tag', default='gemma3-4b-ollama', help='results go to outputs/architecture_comparison/<tag>/; required (and must not be the gemma3 one) with --provider featherless')
    a = p.parse_args()
    if a.provider == 'featherless' and a.tag == 'gemma3-4b-ollama':
        raise SystemExit('--tag is required with --provider featherless (the default folder holds the preserved gemma3 baseline)')

    _load_dotenv()
    if a.provider == 'featherless':
        if not a.model:
            raise SystemExit('--model is required with --provider featherless')
        os.environ['COMPARISON_PROVIDER'] = 'featherless'
        os.environ['COMPARISON_LLM_MODEL'] = a.model
    else:
        os.environ.pop('COMPARISON_PROVIDER', None)  # a stale value must not send clinicProj to a different model than ClaimGuard
        os.environ.pop('COMPARISON_LLM_MODEL', None)
    _check_provider(a.provider)
    out_dir = OUT_ROOT / a.tag
    claims = sample_claims(a.claims, a.sample_size)
    print(f'{len(claims)} claim(s) sampled from {a.claims}')

    if a.system in ('claimguard', 'both'):
        run_system(claims, _claimguard_runner(a.provider, a.model), 'claimguard', out_dir / 'claimguard.jsonl')
    if a.system in ('clinicproj', 'both'):
        run_system(claims, _clinicproj_runner(), 'clinicproj', out_dir / 'clinicproj.jsonl')


if __name__ == '__main__':
    main()
