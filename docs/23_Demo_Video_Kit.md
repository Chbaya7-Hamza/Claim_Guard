# 23. Demo Video Kit (3 minutes maximum)

Everything a teammate needs to record the Phase 1 demo video ("a short video demonstration of the MVP"). **Hard cap: 3:00. The run sheet below is timed to 2:55.** Nothing here needs an API key, the internet or a special account.

The video has four parts. The talker is on camera in parts 1 and 4, narrates the terminal in part 2, and walks through four pieces of code in part 3.

| Part | Clock | What the viewer sees |
|---|---|---|
| 1. Face | 0:00 to 0:25 | The talker, full screen |
| 2. Live demo | 0:25 to 1:47 | The terminal running the real pipeline, then the review page in a browser |
| 3. Code walk | 1:47 to 2:35 | Four files in the editor, each opened at an exact line |
| 4. Face | 2:35 to 2:55 | The talker, full screen, with the repository link |

## 1. What the video must show

A judge should leave knowing five things:

1. The system reads FHIR, CSV and JSONL and does not choke on bad records.
2. Fifteen deterministic rules give findings with evidence and a next step, and the same claim always gets the same answer.
3. Missing data is never a pass.
4. The AI only explains. It cannot approve a claim, change a status or invent evidence.
5. A human decides, the audit log is tamper-evident, and a correction is rechecked as a new run.

## 2. Before you record (15 minutes)

Do these once, then rehearse the full run with a timer at least twice.

| Step | How |
|---|---|
| Get the code | `git clone https://github.com/PublisherX02/Claim_Guard.git`, `cd Claim_Guard`, then follow "Install and run" in `README.md` |
| **Use a checkout that has the final code** | Code shot (d) shows the strict anchor check in `src/audit_log.py`. It exists on branch `phase1-hardening-and-defense` until that pull request is merged. Film from that branch, or after the merge |
| Check the demo works | `python scripts/demo.py --delay 0` finishes in about 2 seconds and ends with "What you saw" |
| Terminal | Dark background, font size 18 or larger, window about 110 columns wide. Windows: `.venv\Scripts\python.exe scripts\demo.py ...` if the environment is not activated |
| Pre-open the code (do not hunt for files on camera) | In your editor, open four tabs at these lines (VS Code: `code -g <file>:<line>`): `rules/core.yar:543`, `src/facts_extractor.py:29`, `src/llm_adapter.py:268`, `src/audit_log.py:405`. Line numbers can shift after edits; the function names are in the run sheet as a fallback |
| Pre-open the picture | `docs/figures/architecture.png` in a viewer, for a cutaway if you want one |
| Recorder | OBS Studio: scene "Face" (camera full screen) and scene "Screen" (terminal or editor, optional small face bubble in a corner). 1080p, 30 fps, microphone on |
| Clean screen | Close notifications. Never show `.env`, an API key, your email or personal folder paths |

## 3. The run sheet

Read the lines in your own words; they are written at about 150 words per minute, so a line that runs long will push the video past 3:00. Times are targets.

### Part 1: Face (0:00 to 0:25)

**Show:** the talker, camera full screen. **Launch:** nothing.

> "Hi, I'm [name] from team [team]. This is ClaimGuard AI. Insurers receive claims with mistakes: wrong dates, missing authorizations, the wrong currency. Checking them by hand is slow and inconsistent. ClaimGuard checks each claim against fifteen rules first, explains every problem in plain language, and a human always decides. Every claim you will see is synthetic."

### Part 2: Live demo (0:25 to 1:47)

**Switch OBS to "Screen". In the terminal, type and run exactly:**

```
python scripts/demo.py --delay 9
```

The demo prints one scene instantly, waits 9 seconds, then prints the next. The last scene has no wait. So the scenes appear at these moments after you press Enter:

| Clock | Scene that appears | Point at | Say (one breath, about 9 seconds) |
|---|---|---|---|
| 0:25 | 1. Ingestion | The "quarantined" lines | "Claims arrive as FHIR, CSV or JSONL. Damaged records are quarantined with a reason, good ones continue. Nothing is lost and nothing becomes a pass." |
| 0:34 | 2. Rule engine | One `[ FAIL ]` line, its `evidence` and `next step` | "Fifteen deterministic rules. Each failure names the rule, the exact evidence and the next step. The same claim always gets the same answer." |
| 0:43 | 3. Unknown is never a pass | The `[UNABLE ]` lines | "Now we blank fields on a claim. The answer is not a pass. The rules say unable to assess. Unknown is never a pass." |
| 0:52 | 4. The AI step | The line `model answers accepted: 0`, then `verdicts identical to the honest run: True` | "The AI only explains. A simulated model tries to approve the claim and invent evidence. Every answer is rejected and the verdicts do not change." |
| 1:01 | 5. The audit log | The hash lines | "Every check and AI action goes into a hash chain. The AI's question is logged before the model is called." |
| 1:10 | 6. A tamper attempt | The line `verify: DETECTED` | "Someone edits the log to turn a fail into a pass. Verification catches it at once: detected." |
| 1:19 | 7. Human review | The three `demo-reviewer ->` decision lines, then `Recheck ... R001 FAIL -> PASS` | "A reviewer confirms, dismisses with a required reason, or requests information. A correction is rechecked as a new run. The original is never edited." |
| 1:28 | 8. The review page | The `wrote ...review.html` line | (let it sit, then cut to the browser) |

**At 1:35, open the review page.** In a second terminal tab or the Start menu run:

```
start outputs\demo\review.html
```

(Mac or Linux: `open outputs/demo/review.html`.) In the browser set the Status filter to FAIL, click one finding so its evidence shows, and record one decision. Say: *"This is the offline review page. Filter by failures, see the evidence exactly as submitted, and record a decision with a reason."* Stop at 1:47.

### Part 3: Code walk (1:47 to 2:35), four shots of about 12 seconds

**Show:** the editor, full screen, tab already open at the line. Highlight the named lines with the cursor. **Launch:** nothing; do not run anything in this part.

| Clock | File and line | Point at | Say |
|---|---|---|---|
| 1:47 | `rules/core.yar`, line 543, rule `R015_fail` | The `rule_id`, the `outcome` and the single pattern line | "Rules are plain text in YARA-X. A rule can only match a pattern. It cannot make a network call, write a file or loop forever. That is why the AI cannot override a verdict." |
| 1:59 | `src/facts_extractor.py`, line 29, function `_q` | The `quote(str(value), safe='')` line | "Claim data is percent-encoded before it becomes a fact, so a value cannot forge a finding. We tested forged values: none got through with this, thousands did without it." |
| 2:11 | `src/llm_adapter.py`, line 268, function `check_grounding` | The list of checks, then `ExplanationOutput` at line 42 if time allows | "Every model reply must match a strict schema and pass a grounding check. It cannot approve, invent evidence or change the review flag. If it fails, the engine's own text is used." |
| 2:23 | `src/audit_log.py`, line 405, function `verify_with_anchor` | The `strict` parameter and the "unanchored row" check | "The audit log is a hash chain plus an anchor. Verification also rejects rows added after the anchor. Tamper-evident, not immutable, and we say so." |

### Part 4: Face (2:35 to 2:55)

**Show:** the talker, camera full screen. Put the repository link on screen as a caption for the last five seconds. **Launch:** nothing.

> "On the public data all fifteen rules match the answer key, nine thousand of nine thousand. We chose the AI setup through four rounds of experiments and tested our design decisions, all documented in the repository. Next: login and a web review interface. The code and documents are on GitHub: PublisherX02 slash Claim underscore Guard. Thank you."

## 4. Things to say, and things not to say

Say:

- "Synthetic", "fictional", "educational" (at the start, and once near the end if there is time).
- "The engine decides, the model explains."
- "Tamper-evident", never "tamper-proof".
- "These checks passed", never "the claim is valid" or "approved".

Do not say:

- That the system makes clinical, coverage or payment decisions.
- That the audit log is immutable (`docs/16_Audit_Log_Design.md` says what that would need).
- That reviewer login exists. It does not yet.
- That the reviewer in scene 7 is a real person. It is a scripted placeholder and the screen says so.
- Any number that is not in `README.md` or `docs/27_Decisions_Proofs_and_Defense.md`. The figures above (9,000 of 9,000; fifteen rules; four experiment rounds) are in those files.

## 5. Honest limits to state if asked

- The AI benchmarks are automated metrics on a small set of cases.
- Reviewer identity is self-declared.
- With no API key the explanation is a deterministic template, not a model. The demo says which one it is using.
- The answer key is the organisers' public data; a different set may score differently.
- The Architecture B comparison result carries the limits written in `docs/24_Architecture_Comparison.md`. Do not quote its score without them.

## 6. If the video runs long

Cut in this order, and keep every other part:

1. Drop code shot (c) or (d) to one sentence each (saves 10 seconds).
2. Drop the browser segment and end Part 2 at scene 8 (saves 12 seconds).
3. Use `--delay 8` instead of `--delay 9` (saves 7 seconds) and shorten each spoken line.

## 7. Backup plan

| Problem | What to do |
|---|---|
| Garbled characters in the terminal | The demo prints plain ASCII. On Windows run `chcp 65001` first |
| Text too small | Increase the terminal font, or zoom in during editing |
| A scene goes wrong | Run `python scripts/demo.py --delay 9` again; it resets its own folder |
| The recorder cannot capture audio | Record silently and add the voice afterwards; `--delay 9` keeps the pacing even |
| You prefer to talk at your own pace | Run `python scripts/demo.py --pause` and press Enter between scenes, but rehearse to stay under 3:00 |
| Optional live model in scene 4 | Skip it in a 3-minute video. `--live` needs `FEATHERLESS_API_KEY` in `.env` (never show that file) and adds variable delay |

## 8. Checklist before you send the video

- [ ] Length is 3:00 or less (check the exported file, not the recorder)
- [ ] Part 1 and Part 4 show the talker's face
- [ ] The word "synthetic" is said in Part 1
- [ ] The screen shows `verify: DETECTED` in scene 6
- [ ] The four code files were opened at the lines in the run sheet
- [ ] No API key, `.env`, email or personal folder path is visible
- [ ] The final screen shows the repository link
- [ ] Exported as MP4, 1080p
