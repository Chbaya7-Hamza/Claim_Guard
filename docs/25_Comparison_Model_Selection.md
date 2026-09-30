# 25 | Why the comparison is re-run on Qwen2.5-14B-Instruct (Featherless)

## Why the first run was not a fair test
The first run used gemma3:4b via Ollama. That model has no tool-calling, and Architecture B's
agent is a LangGraph ReAct agent that depends on it. All 36 claims failed at the API call,
so Architecture B scored 0 on correctness and rapidness. That measures the model, not the
architecture. The finding is real and stays in docs/24. It is not a verdict on Architecture B.

## Constraints on the replacement model
1. Both systems run the same model, so the model is not a confound.
2. It must return structured `tool_calls`. I probed this directly against Featherless.
3. It should follow a long system prompt reliably, because Architecture B's whole behaviour is one prompt.
4. It should not be a reasoning model, because the adapted harness caps output at 1500 tokens.

## What I tested (probe of 1 tool call, then 6 claims through Architecture B)
| Model | Structured tool calls | 6-claim result |
|---|---|---|
| mistralai/Mistral-Nemo-Instruct-2407 (Architecture A's own pick) | No, emits the call as plain text | Unusable for Architecture B |
| Qwen2.5-7B-Instruct | Yes | Drifted into prose on 1 of 2 claims |
| openai/gpt-oss-20b | Yes | 4/6 parsed; both misses were empty or truncated output, because its reasoning uses up the 1500-token cap I set in the adaptation. That cap is my confound. |
| Qwen2.5-14B-Instruct | Yes | 2/6 strictly parsed; all 4 misses were valid JSON wrapped in prose or code fences |
| Qwen2.5-32B-Instruct | Yes (probe) | Run alone, sequentially: 0/6 parsed; Featherless returned "No successful response received from completion service" on claims it failed; average 89 s per claim |
| Qwen3-32B | Yes (probe) | Run alone, sequentially: 1/6 parsed, 5 service errors of the same kind; average 126 s per claim |

## Decision: Qwen2.5-14B-Instruct
- Its misses are a formatting habit, not a reasoning failure, so a disclosed lenient JSON
  extraction (first `{` to last `}`, flagged `wrapped_json`) recovers them without changing
  Architecture B's logic. Strict and lenient counts will both be reported.
- gpt-oss-20b is rejected because its failures came from my token cap, not from the architecture.
- Qwen2.5-7B is rejected because it drifts from the required output.
- The 32B models are rejected on this account: even run alone they returned service errors and took 89 to 126 s per claim. That is about the provider's capacity for big models, not about the models' quality, so it says nothing on whether they reason better.
- With the lenient JSON extraction, Qwen2.5-14B answered 6/6 screening claims (strict parsing: 2/6), at 33 s average. Nothing else screened got above 4/6.

## Honest caveats for the write-up
- This run is hosted (Featherless), not offline, so the "fully local" claim applies only to the gemma3 run.
- The shared model is not Architecture A's production model (Mistral-Nemo). That is because Architecture B cannot run on it.
- The first 6 screening claims are also in the final 36-claim sample.
- Run Architecture B, then Architecture A, then the security probe one after another. Parallel runs cause concurrency errors.
- Check that Architecture A's `ai_explanations` are real model output and not the template fallback.
  If they are the fallback, rapidness compares LLM calls against no LLM calls.

## Status
Done: the harness is parameterized (`--provider featherless --model ... --tag ...`), the gemma3 evidence is kept under
`outputs/architecture_comparison/gemma3-4b-ollama/`, lenient JSON extraction is recorded beside strict, a hallucination metric
was added, and the 12-claim run plus the `docs/24` rewrite are finished. One thing this doc predicted did not hold: the model
that screened best (6/6 lenient on 6 claims) returned degenerate output on 8 of 12 claims in the full run, so the screen
overstated how well it would do. See `docs/24` for what that means for the result.
