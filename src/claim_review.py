"""Bounded state machine for reviewing one claim, per
docs/05_Architecture_and_AI.md's "Agent behaviour to demonstrate":

    validate input -> resolve policy -> run checks -> retrieve evidence ->
    draft and validate the explanation -> show the reviewer

Each step is a small, named, typed-input function -- the model is never
given open-ended action; the only "tool" it can be said to call is
retrieve_evidence(), which is read-only and can only return a value the rule
engine already resolved onto that finding. On model failure, the
deterministic finding is retained and the fallback is marked (never omitted).

review_package() returns three SEPARATE structures -- rule_results,
ai_explanations, run_trace -- deliberately never merged into one record.
"AI explanation helper ... cannot change rule results" (docs/05) is enforced
structurally: nothing here ever writes into a rule_results dict. Run-level
trace metadata (run ID, input hash, rule/model/prompt versions, tool errors)
is stored separately from the claim-rule results themselves, per docs/05's
closing requirement.
"""
import hashlib
import json
import time
import uuid
from pathlib import Path

from audit import digest
from engine_core import validate_transport
from yara_engine import evaluate as run_rule_checks, engine_code_hash, pack_hash
from llm_adapter import MockExplanationProvider, build_prompt, default_provider, explain_with_fallback, omitted_reasons

ROOT = Path(__file__).resolve().parents[1]
PROMPT_VERSION = (ROOT / 'prompts' / 'explain_findings.md').read_text(encoding='utf-8').splitlines()[0].lstrip('# ').strip()
NEEDS_EXPLANATION = {'FAIL', 'UNABLE_TO_ASSESS'}
# The question a model is asked about a finding, in the terms of the deterministic verdict.
VERDICTS = {'FAIL': 'violation_detected', 'UNABLE_TO_ASSESS': 'cannot_determine'}
# What the AI is allowed to do with a finding. It never edits a claim or a result; every AI
# action hands the finding to a person. 'auto_correct' is deliberately not a possible value.
AI_ACTION_TYPE = 'human_escalation'


class IngestionError(Exception):
    """The claim failed the transport contract. Quarantine and report
    separately -- never silently drop it or let it become a passed claim."""


def validate_input(claim: dict) -> dict:
    """Step 1 (named tool, typed input: dict). Raises IngestionError instead
    of silently accepting a malformed envelope."""
    try:
        validate_transport(claim)
    except ValueError as e:
        raise IngestionError(str(e)) from e
    return claim


def resolve_policy(claim: dict, cfg: dict) -> dict | None:
    """Step 2 (named tool, typed input: claim + cfg). Returns the matching
    policy dict, or None -- never an invented fallback policy."""
    return cfg['policies'].get(claim['policy_id'])


def run_checks(claim: dict, cfg: dict, tool_errors: list = None) -> list[dict]:
    """Step 3 (named tool, typed input: claim + cfg). The 15 structured
    rule-engine results, including UNABLE_TO_ASSESS and NOT_APPLICABLE."""
    return run_rule_checks(claim, cfg, tool_errors)


def retrieve_evidence(finding: dict, path: str):
    """Step 4 (named tool, typed input: finding + JSON-pointer path).
    Read-only: can only return a value the rule engine already resolved onto
    this finding's own evidence list -- never re-reads the claim, never
    reaches into any other finding or source."""
    for e in finding['evidence']:
        if e['path'] == path:
            return e['value']
    raise KeyError(f'{path!r} is not evidence on this finding')


def draft_and_validate_explanation(finding: dict, rule: dict, provider, fallback,
                                    untrusted_note: str = None) -> dict | None:
    """Step 5 (named tool, typed input: finding + rule). Only called for
    FAIL/UNABLE_TO_ASSESS -- a PASS/NOT_APPLICABLE finding has nothing to
    explain. Delegates to explain_with_fallback(), which never raises."""
    if finding['status'] not in NEEDS_EXPLANATION:
        return None
    output, used_fallback, error, latency_ms = explain_with_fallback(
        provider, fallback, finding, rule, untrusted_note)
    usage = getattr(provider, 'last_usage', None) if not used_fallback else None
    return {
        'rule_id': finding['rule_id'],
        'output': output,
        'used_fallback': used_fallback,
        'error': error,
        'latency_ms': round(latency_ms, 1),
        'usage': usage,
        'engine_explanation': finding['explanation'],
        'omitted_engine_reasons': omitted_reasons(finding['explanation'], output['explanation']),
        'attempts': getattr(provider, 'last_attempts', None) if not used_fallback else None,
    }


def input_hash(claim: dict) -> str:
    return hashlib.sha256(json.dumps(claim, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def _hook(hooks, name, *args):
    """Call an optional lifecycle hook. Exceptions are NOT swallowed: hooks write the audit
    trail ahead of each action, so if the record cannot be written the action must not happen."""
    fn = getattr(hooks, name, None) if hooks is not None else None
    if fn is not None:
        fn(*args)


def build_ai_request(run_id: str, finding: dict, rule: dict, provider, untrusted_note: str = None) -> dict:
    """Everything worth recording about the question put to the AI, computed BEFORE the call."""
    try:
        prompt_hash = hashlib.sha256(build_prompt(finding, rule, untrusted_note).encode('utf-8')).hexdigest()
        prompt_error = None
    except Exception as e:  # e.g. a finding with no evidence a model could cite
        prompt_hash, prompt_error = None, f'{type(e).__name__}: {e}'
    return {
        'request_id': str(uuid.uuid4()), 'run_id': run_id, 'claim_id': finding['claim_id'],
        'rule_id': finding['rule_id'],
        'question': (f"Explain for a human reviewer why rule {finding['rule_id']} returned "
                     f"{finding['status']} for this claim."),
        'deterministic_status': finding['status'], 'verdict': VERDICTS[finding['status']],
        'requires_human_review': finding['requires_human_review'],
        'finding_hash': digest(finding), 'prompt_version': PROMPT_VERSION, 'prompt_hash': prompt_hash,
        'prompt_error': prompt_error,
        'untrusted_note_present': bool(untrusted_note),
        'untrusted_note_hash': hashlib.sha256(untrusted_note.encode('utf-8')).hexdigest() if untrusted_note else None,
        'provider': type(provider).__name__, 'model': getattr(provider, 'model', 'deterministic-template'),
        'action_type': AI_ACTION_TYPE,
    }


def review_package(claim: dict, cfg: dict, provider=None, fallback=None,
                    untrusted_note: str = None, hooks=None, run_id: str = None) -> tuple:
    """Step 6: run the full bounded sequence for one claim and package the
    result for the reviewer. Returns (rule_results, ai_explanations,
    run_trace):

    - rule_results: the 15 schema-exact records from the rule engine, or
      None if the claim failed ingestion.
    - ai_explanations: list of draft_and_validate_explanation() outputs for
      every FAIL/UNABLE_TO_ASSESS finding (None entries filtered out).
    - run_trace: run_id, claim_id, input_hash, rule pack version/hash,
      whether the policy resolved, model + prompt version, any tool errors,
      start/finish times -- kept separate from rule_results so a correction
      always produces a new run rather than mutating the old one.

    Optional `hooks` receive write-ahead callbacks, in this order: on_start (input accepted),
    on_checks (all 15 results, before any AI call), then for each explained finding
    before_ai (the request, BEFORE the model is called) and after_ai (the outcome).
    """
    run_id = run_id or str(uuid.uuid4())
    started_at = time.time()
    in_hash = input_hash(claim)
    tool_errors = []

    provider = provider or default_provider()
    fallback = fallback or MockExplanationProvider()

    try:
        claim = validate_input(claim)
    except IngestionError as e:
        return None, None, {
            'run_id': run_id, 'claim_id': claim.get('claim_id', 'UNKNOWN') if isinstance(claim, dict) else 'UNKNOWN',
            'input_hash': in_hash, 'ingestion_error': str(e),
            'model': getattr(provider, 'model', 'mock'), 'prompt_version': PROMPT_VERSION,
            'tool_errors': tool_errors,
            'started_at': started_at, 'finished_at': time.time(),
        }
    _hook(hooks, 'on_start', run_id, claim, in_hash, started_at)

    policy = resolve_policy(claim, cfg)
    rule_results = run_checks(claim, cfg, tool_errors)
    rule_defs = {r['rule_id']: r for r in cfg['rules']}
    _hook(hooks, 'on_checks', run_id, claim, rule_results)

    ai_explanations = []
    for finding in rule_results:
        if finding['status'] not in NEEDS_EXPLANATION:
            continue
        rule = rule_defs[finding['rule_id']]
        request = build_ai_request(run_id, finding, rule, provider, untrusted_note)
        _hook(hooks, 'before_ai', request)  # write-ahead: recorded before the model is asked
        try:
            drafted = draft_and_validate_explanation(finding, rule, provider, fallback, untrusted_note)
        except Exception as e:
            # explain_with_fallback already catches provider failures; this
            # only fires for a genuine bug in the orchestration step itself,
            # and is recorded rather than allowed to abort the whole claim.
            tool_errors.append(f"{finding['rule_id']}: {type(e).__name__}: {e}")
            drafted = None
        if drafted is not None:
            ai_explanations.append(drafted)
        _hook(hooks, 'after_ai', request, drafted, tool_errors[-1] if drafted is None else None)

    run_trace = {
        'run_id': run_id,
        'claim_id': claim['claim_id'],
        'input_hash': in_hash,
        'rule_pack_hash': pack_hash(),
        'engine_code_hash': engine_code_hash(),
        'rule_versions': sorted({r['version'] for r in cfg['rules']}),
        'policy_resolved': policy is not None,
        'model': getattr(provider, 'model', 'mock'),
        'prompt_version': PROMPT_VERSION,
        'tool_errors': tool_errors,
        'started_at': started_at,
        'finished_at': time.time(),
    }
    return rule_results, ai_explanations, run_trace
