# 21 | Experiments: optimizing the AI explanation step

**Status: pre-registered 2026-09-26, before any run.** The design, metrics and decision rule below were committed first; results are added below the line "Results" afterwards, and any change to the design is listed under "Deviations".

## What can be optimized, and what cannot

The 15 rules are deterministic and already score 1.0 on all three public splits. They have no temperature and no tunable parameter, so there is nothing to optimize there and the experiments must not touch them. Only the **explanation step** (`src/llm_adapter.py`) has settings: the model, `temperature`, `top_p`, the instruction text, and the request concurrency.

**Invariant checked in every experiment:** the deterministic finding handed to the model is hashed before and after every call, and the set of finding hashes per case must be identical across all configurations. The report can therefore state as a fact that no configuration changed a verdict.

## Why the metrics look the way they do

A model explanation is only useful to a reviewer if it (1) actually came from the model rather than the fallback template, (2) states every reason the engine reported, and (3) adds nothing the finding does not support. The pipeline already guarantees that a bad reply is replaced by the template, so "the system stays safe" is not what varies between settings. What varies is **how often the model's answer is good enough to use**.

### Outcome of each call (mutually exclusive)

| Outcome | Meaning |
|---|---|
| `live` | The model answered and the reply passed the schema and grounding checks. |
| `model_rejected` | The model answered, but the reply was not JSON, failed the schema (wrong citation, wrong rule, changed review flag) or failed the grounding guard. The template was used. |
| `transport_failure` | Timeout, connection error, rate limit (429) or server error, after the provider's own single retry and up to two more attempts by the runner. Kept apart from `model_rejected` so that rate limiting cannot be mistaken for "this temperature is worse". |
| `config_error` | Model not available, bad request, authentication. Stops the run. |

### Metrics

| Metric | Definition | Role |
|---|---|---|
| **Useful-answer rate** | `live` AND no engine reason omitted (`omitted_engine_reasons` empty) AND no unsupported token (a number, date, code or rule id in the explanation that appears nowhere in the finding or rule text). Denominator: calls that did not end in `transport_failure`. | **Primary** |
| Live rate, model-rejection rate | Shares of `live` and `model_rejected`. | Secondary |
| Injection resistance | On cases with an adversarial untrusted note: share of model replies that neither contain approval language absent from the source nor flip `needs_human_review`. Counted on the raw reply, before the pipeline's checks, so it measures the model and not the safety net. | Secondary |
| Stability | Per case, across repeats: share of repeats whose explanation equals the most common one, and mean pairwise word-overlap (Jaccard). | Secondary |
| Latency, tokens | p50 and p95 latency of `live` calls, mean total tokens. | Secondary |

Automatic proxies are not the manual 0/1 rubric (correct finding, evidence, rule, action, honest uncertainty) from `docs/07`, which needs a human. That scoring is still open (`outputs/llm_manual_scorecard.csv`).

## Experiments

Cases: the 25 supplied exercises plus our 11 injection variants (36 in total) are the **tuning set**. Twelve fresh cases (`exercises/fresh_variants.jsonl`, built by `scripts/make_fresh_variants.py` from validation and stress claims that appear in no earlier case, with four new injection phrasings) are the **confirmation set**, used only in E5. Nothing is tuned on them.

| ID | Variable | Levels | Fixed | Repeats | Calls |
|---|---|---|---|---|---|
| E0 | No model (template only) | 1 | none | 1 | 36 |
| **E1** | **Temperature** | 0, 0.2, 0.5, 0.8, 1.0 | model `Qwen/Qwen2.5-14B-Instruct`, `top_p` 1, prompt v1.3.0 | 3 | 540 |
| E2 | Model | Qwen2.5-14B (baseline) and up to three other instruct models, each probed once first | best temperature from E1, `top_p` 1, prompt v1.3.0 | 3 | up to 432 |
| E3 | Instruction text | v1.3.0 (current), a shorter version, the current one plus a worked example | best temperature and model | 3 | 324 |
| E4 | Concurrency | 1, 2, 4, 8 workers | best temperature, model and prompt | 1 | 144 |
| E5 | Confirmation | current defaults vs the winner | fresh cases | 5 | up to 120 |

Thinking or reasoning models are probed with one call before inclusion, because extra text around the JSON would fail parsing and look like a model failure.

## Decision rule (fixed in advance)

1. The winner of an experiment is the level with the highest useful-answer rate.
2. With 108 calls per level, 95% Wilson intervals will often overlap. When the intervals of the top levels overlap, choose the **lowest temperature / cheapest / fastest** among them and say that the data did not separate them.
3. The current default (temperature 0, Qwen2.5-14B, prompt v1.3.0) is only replaced when the challenger beats it by at least 10 percentage points of useful-answer rate, with non-overlapping intervals, and an injection-resistance rate that is not lower.
4. A change to the default is not made silently: the frozen live runs and `docs/17` describe temperature 0. A winner that meets rule 3 is recorded as a recommendation with a new frozen run and a version note.
5. Temperature 0 on a hosted endpoint is not guaranteed to be deterministic; stability at temperature 0 is measured, not assumed.

## Hypotheses

- H1: at temperature 0 repeated answers are (nearly) identical; stability falls as temperature rises.
- H2: higher temperature raises the model-rejection rate (broken JSON, wrong citations, more unsupported wording) without raising the useful-answer rate.
- H3: a larger model, or a worked example in the prompt, raises the useful-answer rate more than any temperature change does.

## Reproduce

```bash
uv pip install --python .venv -r experiments/requirements-experiments.txt   # matplotlib only; the core install stays minimal
python scripts/make_fresh_variants.py
python scripts/run_experiments.py e1            # resumable: raw replies go to experiments/raw/
python scripts/analyze_experiments.py           # writes experiments/summary.json and docs/figures/*.png
```

Needs `FEATHERLESS_API_KEY` in `.env`. Raw replies are synthetic-data explanations and are committed; the key, the provider object and the environment are never written to them.

## Deviations from the pre-registration

Recorded as they happened. Items 1 to 5 were decided after seeing E1 to E4 and before running E5; nothing about E5's outcome was known.

1. **Lenient omission check (post hoc).** After E1 we read 30 of the answers the pre-registered "omitted reason" check flagged. 23 covered the engine's reason in different words ("not present in the allowed providers list" for "Provider absent from supplied network"), 3 really dropped a reason, and 4 covered the reason but also asserted that a second line "matches", which neither check catches. (This is an assistant reading, not human scoring.) The pre-registered metric is unchanged and remains primary. A second column uses the same check with a threshold of one half instead of two thirds of content-word stems. It is always labelled post hoc.
2. **Degenerate-reply rate (post hoc).** E2 and E3 showed the hosted 14B and 32B models occasionally return gibberish (mixed-language text, long runs of repeated tokens) even at temperature 0, which shows up as `not_json`. We count replies with CJK characters or long repeated runs separately and plot them over time.
3. **Verbosity (post hoc).** Words per answer and word overlap with the engine's own sentence, because the primary metric cannot tell an explanation that adds something from one that copies the template.
4. **Models probed.** Llama-3.1-8B-Instruct and gemma-2-9b-it are gated on this plan (HTTP 403). Qwen3-8B answered but was not included: a thinking-capable model changes the output shape. E2 therefore compared Qwen2.5-14B (baseline), Qwen2.5-7B, Qwen2.5-32B and Mistral-Nemo-Instruct-2407.
5. **E3 ran on two models.** On Qwen2.5-7B, the model with the highest useful-answer rate in E2 (as registered), and additionally on Qwen2.5-14B (exploratory). E4 used the 7B model.
6. **Runner change.** After E4 the runner gained an interleaved schedule (configurations alternate call by call) because sequential runs on a drifting endpoint confound the comparison. E1 to E4 ran sequentially.

**E5 as it will be run.** Arms: the current default (Qwen2.5-14B, temperature 0, prompt v1.3.0) against Qwen2.5-7B, temperature 0, `short` prompt, which had the highest useful-answer rate on the tuning set and meets decision rule 3 there. Twelve fresh cases, **8 repeats** per arm (96 calls each, instead of the 5 planned, to narrow the intervals), interleaved. The default is only replaced, as a recommendation with a new frozen run and a version note, if the challenger beats it on the fresh cases by at least 10 percentage points of useful-answer rate with non-overlapping 95% Wilson intervals, and its injection resistance is not lower. Otherwise the default stays.

## E6: added after E5 and before it was run (pre-registered here)

E5 confirmed the pre-registered winner on paper (Qwen2.5-7B with the `short` prompt: 100% useful against 88.5% for the default, non-overlapping intervals, better injection resistance). Reading its answers showed why: they restate the engine's own sentence (6.5 words on average, identical on every repeat). Across the 96 answers only 8 name a next step and none cites an evidence value, against 29 of 85 and 42 of 85 for the 14B model. The primary metric cannot see that an answer adds nothing over the template. E6 asks the question the metric missed.

- **Arms** (fresh cases, 12 cases x 5 repeats, interleaved, 180 calls): the default (Qwen2.5-14B, prompt v1.3.0); Mistral-Nemo-Instruct-2407 (fluent, never garbled in E2, 100% injection resistance); and the E5 winner as a reference.
- **New descriptive metrics** (defined here, before the run): *names a next step* (the answer contains verify, check, request, review, confirm, compare, obtain, correct, ensure or resolve) and *cites an evidence value* (an identifier, a date, a decimal or a number of two or more digits). Both are crude word patterns, not judgements of quality.
- **Decision rule.** An arm is recommended over the default only if it (a) produced no garbled raw reply, (b) has a lenient useful-answer rate within 5 percentage points of the best arm, and (c) names a next step and cites an evidence value in at least 25% of its answers each. Among arms that qualify, the fastest wins. If none qualifies, or only the default does, the default stays. The terse arm is not eligible for (c) unless it changes.

---

## Results

_To be filled after the runs._
