# 23. Demo Video Kit

Everything a teammate needs to record the Phase 1 demo video ("a short video demonstration of the MVP") without having built the system. Target length: **4 to 5 minutes**. Nothing here needs an API key, the internet or a special account, except the optional live-model shot.

## 1. What the video must show

A judge should leave the video knowing five things, in this order:

1. The system reads real-world claim formats (FHIR, CSV, JSONL) and does not choke on bad records.
2. Fifteen deterministic rules produce findings with evidence and a next step, and the same claim always gets the same answer.
3. Missing data is never treated as a pass.
4. The AI only explains. It cannot approve a claim, change a status or invent evidence, and the audit log proves it.
5. A human decides, and a correction is rechecked as a new run.

The one-command demo (`scripts/demo.py`) walks through all five on screen, so the recording is mostly the terminal plus two short cutaways.

## 2. Before you record (10 minutes)

| Step | How |
|---|---|
| Get the code | `git clone https://github.com/Chbaya7-Hamza/Claim_Guard.git` then `cd Claim_Guard` (GitHub may redirect to the moved repository name; that is fine) |
| Install | Follow "Install and run" in `README.md` (Python 3.10 or newer, `uv` or `pip`) |
| Check it works | `python scripts/demo.py --delay 0` should finish in about 2 seconds and end with "What you saw" |
| Terminal | Windows Terminal or any terminal, dark background, font size 16 or larger, window about 110 columns wide (the demo uses 100) |
| Recorder | OBS Studio (free), Xbox Game Bar (`Win+G`), or QuickTime on Mac. 1080p, 30 fps, microphone on |
| Clean screen | Close notifications, hide the desktop clutter, and do not show `.env` or any API key |
| Optional live shot | Put `FEATHERLESS_API_KEY=...` in `.env` (never show the file), then use `--live` in the scene 4 take |

Two ways to run the demo:

```bash
python scripts/demo.py --pause        # you press Enter between scenes; best while talking live
python scripts/demo.py --delay 6      # hands-free: pauses 6 seconds after each scene; best when you add the voice later
python scripts/demo.py --delay 6 --live   # same, and scene 4 uses the real model
```

On Windows use `.venv\Scripts\python.exe scripts\demo.py ...` if the environment is not activated.

## 3. Shot list and narration (about 4 min 40 s)

Read the narration in your own words; the lines are a guide, not a script to memorize. Times are a target.

| # | Time | On screen | Say |
|---|---|---|---|
| 0 | 0:00 to 0:20 | Title slide or the top of `README.md` | "This is ClaimGuard AI, a pre-validation copilot for synthetic healthcare claims. It checks a claim against fifteen rules before a person reviews it. Every claim here is invented, and a human always makes the decision." |
| 1 | 0:20 to 0:50 | `docs/figures/architecture.png` full screen | "The rule engine decides. The language model only explains. The engine is deterministic and has no network access. The model sees one finding at a time, cannot write a file and cannot change a status. Everything is written to a tamper-evident audit log." Trace with the cursor: files in, ingestion, rules, results, gateway, audit log, reviewer. |
| 2 | 0:50 to 1:20 | Terminal: run `python scripts/demo.py --delay 6`. **Scene 1** | "Claims arrive as FHIR bundles, CSV folders or JSONL. All three are normalized into one format. Here is a deliberately damaged file: three bad lines are quarantined with a reason, and the good ones still go through. Nothing is lost and nothing becomes a pass." |
| 3 | 1:20 to 1:55 | **Scene 2** | "Here is a claim with four failures. Each finding names the rule, the severity, the exact evidence, a pointer into the claim plus the value we saw, and what a human should do next. And this clean claim: all checks pass, which means only that these fifteen checks passed, never that it is approved." |
| 4 | 1:55 to 2:15 | **Scene 3** | "What if the data is missing? We blank the fields on one claim. The answer is not a pass. Fourteen rules say Unable to assess, and each one says what is missing. Unknown is never a pass." |
| 5 | 2:15 to 2:50 | **Scene 4** | "Now the AI step. The model writes a plain-language explanation, but its reply must fit a strict schema, cite only evidence that exists, keep the review flag, and pass a grounding check. Here we simulate a misbehaving model that tries to approve the claim and invent evidence. All four answers are rejected and replaced with the engine's own text. The verdicts are identical." If recorded with `--live`, add: "and this is a real model writing the explanation." |
| 6 | 2:50 to 3:25 | **Scene 5, then Scene 6** | "Every check, AI action and decision goes into a hash chain. The AI's question is logged before the model is called. Now watch: someone edits the log and turns a fail into a pass. Verification detects it at once." Point at the word DETECTED. |
| 7 | 3:25 to 4:05 | **Scene 7, then Scene 8** | "A reviewer confirms, requests information, or dismisses with a reason. A reason is required. When a claim is corrected, it is rechecked as a new run: the original claim is never edited. This is the offline review page." Then open `outputs/demo/review.html` in a browser, filter Status = FAIL, and record one decision. |
| 8 | 4:05 to 4:40 | `docs/figures/scoreboard_e10b.png`, then the README "Results" table | "On the public splits, all fifteen rules match the answer key, nine thousand of nine thousand results. We tested the AI step across four experiment rounds and chose the configuration by rules we wrote before running. Every benchmark is above eighty-five percent. Next phases: the review interface as a mobile app on a local API, and authentication." |

Keep the whole video in one continuous take where possible. If a scene goes wrong, run the command again; the demo is repeatable and resets its own folder.

## 4. Things to say, and things not to say

Say:

- "Synthetic", "fictional", "educational". Say it at the start and once more near the end.
- "The engine decides, the model explains."
- "Tamper-evident", not "tamper-proof".
- "These checks passed", never "the claim is valid" or "approved".

Do not say:

- That the system makes clinical, coverage or payment decisions.
- That the audit log is immutable. It is tamper-evident; `docs/16_Audit_Log_Design.md` says what real immutability would need.
- That reviewer login exists. It does not yet.
- That the demo reviewer in Scene 7 is a real person. It is a scripted placeholder, and the screen says so.
- Any percentage that is not in the README.

## 5. Honest limits to state if asked

- The AI benchmarks are mechanical proxies on a small set of cases; nobody has hand-scored the answers yet.
- Reviewer identity is self-declared.
- With no API key the explanation is a deterministic template, not a model. The demo says which one it is using.
- The public answer key is matched 100%, but that is the organizers' data; a hidden set may differ.

## 6. Backup plan

| Problem | What to do |
|---|---|
| Live model is slow or fails in Scene 4 | Record without `--live`. The demo says "deterministic template" on screen, and the safety-net part still works, because it uses a simulated model |
| Unicode or garbled characters in the terminal | The demo prints plain ASCII. If you see garbling, run `chcp 65001` first (Windows) |
| The text is too small in the recording | Increase the terminal font, or run `python scripts/demo.py --delay 8` and zoom in during editing |
| You need a still of the review page | `outputs/demo/review.html` is an offline page: open it in any browser |
| The recorder cannot capture audio | Record the screen silently and add the voice-over afterwards, using `--delay 6` so the pacing stays even |

## 7. Checklist before you send the video

- [ ] Length is between 3 and 5 minutes
- [ ] The word "synthetic" is said at the start
- [ ] All five points in section 1 are visible
- [ ] Scene 6 shows DETECTED
- [ ] No API key, `.env`, email or personal folder path visible on screen
- [ ] The final screen shows the repository link
- [ ] Exported as MP4, 1080p
