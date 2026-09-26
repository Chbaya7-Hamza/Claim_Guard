"""Run the AI-explanation experiments in docs/21_Experiments.md through the production path.

Every call goes through claim_review.draft_and_validate_explanation -> llm_adapter.explain_with_fallback, so it includes
the orchestrator's schema and grounding checks and the deterministic fallback, exactly as the pipeline does. The raw model
reply is kept next to the outcome so failures can be classified afterwards.

Usage (resumable: a finished (config, case, repeat) is never called twice):
    python scripts/run_experiments.py e1                       # temperature sweep, 36 cases x 3 repeats
    python scripts/run_experiments.py e2 --temperature 0 --models Qwen/Qwen2.5-7B-Instruct,Qwen/Qwen2.5-32B-Instruct
    python scripts/run_experiments.py e3 --temperature 0 --model Qwen/Qwen2.5-14B-Instruct
    python scripts/run_experiments.py e4 --temperature 0 --prompt current
    python scripts/run_experiments.py e5 --temperature 0 --model Qwen/Qwen2.5-14B-Instruct --prompt fewshot --reps 5
    python scripts/run_experiments.py probe --models a,b     # one call per model, to check it can answer in JSON

Raw output: experiments/raw/<experiment>.jsonl. Nothing secret is written: not the key, the client or the environment.
"""
import argparse
import copy
import hashlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from claim_review import draft_and_validate_explanation
from llm_adapter import FeatherlessExplanationProvider, MockExplanationProvider
from yara_engine import engine_code_hash

RAW = ROOT / 'experiments' / 'raw'
DEFAULT_MODEL = 'Qwen/Qwen2.5-14B-Instruct'
TEMPERATURES = [0, 0.2, 0.5, 0.8, 1.0]
WORKERS_GRID = [1, 2, 4, 8]
PROMPTS = {'current': None, 'short': ROOT / 'prompts' / 'variants' / 'short.md',
           'fewshot': ROOT / 'prompts' / 'variants' / 'fewshot.md'}
TRANSPORT = {'APITimeoutError', 'APIConnectionError', 'RateLimitError', 'InternalServerError', 'TransientProviderError',
             'TimeoutError', 'ConnectionError', 'ReadTimeout', 'ConnectTimeout'}
CONFIG_ERRORS = {'NotFoundError', 'PermissionDeniedError', 'AuthenticationError', 'BadRequestError',
                 'UnprocessableEntityError'}


def classify(error):
    """'transport' | 'config' | 'model' for the error string explain_with_fallback recorded."""
    name = (error or '').split(':', 1)[0].strip()
    if name in TRANSPORT:
        return 'transport'
    if name in CONFIG_ERRORS:
        return 'config'
    return 'model'


class RecordingProvider(FeatherlessExplanationProvider):
    """The production provider, plus a per-thread record of every raw reply (kept even when it is later rejected)."""

    def _complete(self, prompt):
        text = super()._complete(prompt)
        raws = getattr(self._tl, 'raws', None)
        if raws is not None:
            raws.append(text[:3000])
        return text


def load_cases(which):
    names = {'tuning': ['llm_explanation_cases.jsonl', 'injection_variants.jsonl'], 'fresh': ['fresh_variants.jsonl']}[which]
    cases = []
    for name in names:
        for line in (ROOT / 'exercises' / name).read_text(encoding='utf-8').split(chr(10)):
            if line.strip():
                cases.append(json.loads(line))
    return cases


def git_head():
    """Commit id read from .git without running git (this folder may not use subprocess)."""
    g = ROOT / '.git'
    if g.is_file():
        g = Path(g.read_text(encoding='utf-8').split('gitdir:', 1)[1].strip())
    head = (g / 'HEAD').read_text(encoding='utf-8').strip()
    if not head.startswith('ref:'):
        return head
    ref = head.split(' ', 1)[1]
    for base in (g, g.parent.parent if g.parent.name == 'worktrees' else g):
        p = base / ref
        if p.exists():
            return p.read_text(encoding='utf-8').strip()
        packed = base / 'packed-refs'
        if packed.exists():
            for line in packed.read_text(encoding='utf-8').split(chr(10)):
                if line.endswith(' ' + ref):
                    return line.split(' ')[0]
    return 'unknown'


def prompt_text(name):
    path = PROMPTS[name]
    return path.read_text(encoding='utf-8') if path else None


def one_call(cfg, provider, case, rep, extra_retries=2):
    finding, rule, note = case['finding'], case['rule'], case.get('untrusted_note')
    before = hashlib.sha256(json.dumps(finding, sort_keys=True).encode()).hexdigest()
    tries = []
    for attempt in range(extra_retries + 1):
        provider._tl.raws = []
        t0 = time.monotonic()
        drafted = draft_and_validate_explanation(copy.deepcopy(finding), copy.deepcopy(rule), provider,
                                                 MockExplanationProvider(), note)
        wall_ms = (time.monotonic() - t0) * 1000
        error = drafted['error']
        kind = classify(error) if drafted['used_fallback'] else None
        tries.append({'error': error, 'kind': kind})
        if kind == 'config':
            raise SystemExit(f'configuration error for {cfg["cfg_id"]}: {error}')
        if kind != 'transport' or attempt == extra_retries:
            break
        time.sleep(min(30, 2 ** (attempt + 1)))
    after = hashlib.sha256(json.dumps(finding, sort_keys=True).encode()).hexdigest()
    out = drafted['output']
    return {
        'type': 'call', 'exp': cfg['exp'], 'cfg_id': cfg['cfg_id'], 'model': cfg['model'], 'temperature': cfg['temperature'],
        'top_p': cfg['top_p'], 'prompt': cfg['prompt'], 'workers': cfg['workers'], 'case_id': case['case_id'], 'rep': rep,
        'outcome': 'live' if not drafted['used_fallback'] else ('transport_failure' if kind == 'transport' else 'model_rejected'),
        'error': error, 'attempts': drafted.get('attempts'), 'runner_retries': len(tries) - 1, 'all_errors': tries,
        'latency_ms': drafted['latency_ms'], 'wall_ms': round(wall_ms, 1), 'usage': drafted.get('usage'),
        'explanation': out['explanation'], 'cited_paths': out['cited_evidence_paths'], 'cited_rules': out['cited_rule_ids'],
        'needs_human_review': out['needs_human_review'], 'omitted_engine_reasons': drafted['omitted_engine_reasons'],
        'engine_explanation': drafted['engine_explanation'], 'raw_replies': list(provider._tl.raws),
        'finding_hash_before': before, 'finding_hash_after': after, 'ts': time.time(),
    }


def make_provider(cfg):
    return RecordingProvider(model=cfg['model'], temperature=cfg['temperature'], top_p=cfg['top_p'],
                             instructions=prompt_text(cfg['prompt']))


def existing_keys(path):
    done = set()
    if path.exists():
        for line in path.read_text(encoding='utf-8').split(chr(10)):
            if line.strip():
                r = json.loads(line)
                if r.get('type') == 'call':
                    done.add((r['cfg_id'], r['case_id'], r['rep']))
    return done


def run_grid(exp, configs, cases, reps, path, interleave=False):
    RAW.mkdir(parents=True, exist_ok=True)
    done = existing_keys(path)
    lock = threading.Lock()
    fresh_file = not path.exists()
    with path.open('a', encoding='utf-8', newline=chr(10)) as f:
        def emit(rec):
            with lock:
                f.write(json.dumps(rec, ensure_ascii=False) + chr(10))
                f.flush()
        if fresh_file:
            emit({'type': 'manifest', 'exp': exp, 'started': time.time(), 'commit': git_head(),
                  'engine_code_hash': engine_code_hash(), 'n_cases': len(cases), 'reps': reps,
                  'prompt_sha256': {k: hashlib.sha256((prompt_text(k) or (ROOT / 'prompts' / 'explain_findings.md').read_text(encoding='utf-8')).encode()).hexdigest()
                                    for k in PROMPTS},
                  'configs': configs, 'max_tokens': 500, 'timeout_s': FeatherlessExplanationProvider.TIMEOUT})
        providers = {cfg['cfg_id']: make_provider(cfg) for cfg in configs}

        def warmup(cfg):
            # Models load on demand (the first call of a session can take 15+ s). One untimed call per configuration keeps
            # that cold start out of the latency numbers; it is recorded as a warmup, not as data.
            warm = one_call(cfg, providers[cfg['cfg_id']], cases[0], -1, extra_retries=0)
            emit({'type': 'warmup', 'exp': exp, 'cfg_id': cfg['cfg_id'], 'wall_ms': warm['wall_ms'], 'outcome': warm['outcome']})

        # Sequential schedule: finish one configuration before the next (an endpoint that drifts during the run then
        # confounds the comparison). Interleaved schedule: the configurations alternate call by call, so drift hits all equally.
        if interleave:
            schedule = [(cfg, c, r) for r in range(reps) for c in cases for cfg in configs
                        if (cfg['cfg_id'], c['case_id'], r) not in done]
            groups = [(None, schedule)]
        else:
            groups = [(cfg, [(cfg, c, r) for r in range(reps) for c in cases if (cfg['cfg_id'], c['case_id'], r) not in done])
                      for cfg in configs]
        for label_cfg, todo in groups:
            if not todo:
                continue
            for cfg in ([label_cfg] if label_cfg else configs):
                warmup(cfg)
            workers = (label_cfg or configs[0])['workers']
            t0 = time.monotonic()
            n = 0

            def work(item):
                cfg, case, rep = item
                rec = one_call(cfg, providers[cfg['cfg_id']], case, rep)
                emit(rec)
                return rec

            with ThreadPoolExecutor(max_workers=workers) as pool:
                for rec in pool.map(work, todo):
                    n += 1
                    if n % 12 == 0 or n == len(todo):
                        print(f'  {rec["cfg_id"]}: {n}/{len(todo)} calls, last outcome {rec["outcome"]}', flush=True)
            emit({'type': 'batch', 'exp': exp, 'cfg_id': (label_cfg or {'cfg_id': 'interleaved'})['cfg_id'],
                  'workers': workers, 'calls': len(todo), 'wall_s': round(time.monotonic() - t0, 2)})
    print(f'{exp}: done -> {path}')


def cfg(exp, model, temperature, prompt='current', workers=4, top_p=1):
    tag = f'{model.split("/")[-1]}|T{temperature}|p{top_p}|{prompt}' + (f'|w{workers}' if exp == 'e4' else '')
    return {'exp': exp, 'cfg_id': tag, 'model': model, 'temperature': temperature, 'top_p': top_p, 'prompt': prompt,
            'workers': workers}


def probe(models, temperature):
    case = load_cases('tuning')[0]
    for model in models:
        c = cfg('probe', model, temperature)
        t0 = time.monotonic()
        try:
            rec = one_call(c, make_provider(c), case, 0, extra_retries=0)
            print(f'{model}: {rec["outcome"]} in {time.monotonic() - t0:.1f}s '
                  f'{(rec["error"] or "")[:120]} reply={rec["raw_replies"][-1][:100] if rec["raw_replies"] else None!r}')
        except SystemExit as e:
            print(f'{model}: {e}')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('experiment', choices=['e1', 'e2', 'e3', 'e4', 'e5', 'probe'])
    p.add_argument('--model', default=DEFAULT_MODEL)
    p.add_argument('--models', default='')
    p.add_argument('--temperature', type=float, default=0)
    p.add_argument('--prompt', default='current', choices=list(PROMPTS))
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--reps', type=int, default=3)
    a = p.parse_args()
    if a.experiment == 'probe':
        probe([m for m in a.models.split(',') if m] or [a.model], a.temperature)
        return
    if a.experiment == 'e1':
        grid, cases, reps = [cfg('e1', a.model, t, workers=a.workers) for t in TEMPERATURES], load_cases('tuning'), a.reps
    elif a.experiment == 'e2':
        models = [a.model] + [m for m in a.models.split(',') if m and m != a.model]
        grid, cases, reps = [cfg('e2', m, a.temperature, workers=a.workers) for m in models], load_cases('tuning'), a.reps
    elif a.experiment == 'e3':
        grid = [cfg('e3', a.model, a.temperature, pr, workers=a.workers) for pr in PROMPTS]
        cases, reps = load_cases('tuning'), a.reps
    elif a.experiment == 'e4':
        grid = [cfg('e4', a.model, a.temperature, a.prompt, workers=w) for w in WORKERS_GRID]
        cases, reps = load_cases('tuning'), 1
    else:  # e5: current defaults against the chosen setting, on cases nothing was tuned on
        grid = [cfg('e5', DEFAULT_MODEL, 0, 'current', a.workers)]
        chosen = cfg('e5', a.model, a.temperature, a.prompt, a.workers)
        if chosen['cfg_id'] != grid[0]['cfg_id']:
            grid.append(chosen)
        cases, reps = load_cases('fresh'), a.reps
    run_grid(a.experiment, grid, cases, reps, RAW / f'{a.experiment}.jsonl', interleave=a.experiment == 'e5')


if __name__ == '__main__':
    main()
