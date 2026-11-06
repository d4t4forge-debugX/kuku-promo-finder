# Journey Log: Kuku Promo Finder

Running record of everything from start to finish: steps, errors, fixes, decisions,
and every place an AI tool (or I) got something wrong. Feeds the solution doc and interview prep.

Tools used: Claude (planning, code drafts, explanations, reviews) · Gemini API (`gemini-3.8-flash` picker,
`gemini-3.1-pro-preview` judge) · PyCharm · git/GitHub.

## Decisions & assumptions
| # | Decision / assumption | Why | Alternatives considered |
|---|---|---|---|
| 1 | Chose Problem 1 (Find the Promos) | Kuku's real weekly pain; input pack given; every line is timestamped; easy to re-run live in the interview | P2 AI Lawyer (crowded, hallucination-heavy), P3 own problem (hardest to justify) |
| 2 | One OpenAI-compatible client for every provider | Swapping model = edit `.env`, no code change (brief says swappable models will shine) | Separate SDK per provider |
| 3 | Pinned model names, not `-latest` aliases | Aliases can silently change; results must reproduce in the interview | `gemini-flash-latest` |
| 4 | AI answers with line IDs (L012), code looks up timestamps | AI can't invent timestamps; hallucinated IDs are detectable (0 found in 50 eps) | Ask AI for timestamps directly |
| 5 | Hard rules in code (20-60s, hook within 3s, no mid-line cuts, dedupe); taste left to AI | Code never forgets a rule; AI is good at judging drama | Put the rules only in the prompt |
| 6 | Cache every AI result per episode/promo | Re-runs are free and resumable after crashes or rate limits | Re-call AI every run |
| 7 | Separate judge model sees ONLY the clip, like a stranger | Picker's self-scores clustered at 23-27/30 (no signal); judge spread 3-9 | Rank on picker's own scores |
| 8 | Two output lists: Acquisition (Ep 1-15) + Best overall | Viewer who taps a promo lands on Ep 1; a promo from Ep 32 is a bait-and-switch | A: rank on quality only; B: stronger score penalty |
| 9 | Gold set = 5 episodes by fixed rule (4,14,24,34,44), picked blind by me | Avoid cherry-picking; real human baseline | Pick episodes I liked |
| 10 | Keep human-blind and AI-assisted gold sets separate; report only the blind one | AI-revised set copied tool starts (start gap 0.5s) = contaminated | Replace my picks with AI's picks |
| 11 | Policy: cross-check everything (independent auditor, tests, stability, second judge) | Pipeline checking itself can share its own bugs | Trust the pipeline's own validators |
| 12 | Auditor imports NOTHING from src/ and re-reads raw scripts | So it can't share a bug with the pipeline | Reuse parser in the auditor |
| 13 | Tests use a made-up episode, not Kuku's scripts | Confidential data stays off GitHub; tests run anywhere | Test on real scripts |
| 14 | Second judge = openai/gpt-oss-120b on Groq (different company) | Gemini picking AND judging could share taste | Another Gemini/Gemma model |

## AI / tool got it wrong (need at least 1 for the doc)
| When | Tool | What went wrong | How I caught it | Fix |
|---|---|---|---|---|
| Step 3 | Gemini picker | E02-P2 "cliffhanger" was a payoff (groom stunned silent): question already answered | Read the picks by hand; judge later independently flagged it `resolved_inside` | Judge penalty -1.0 + human review flag |
| Step 3 | Gemini picker | Ep 1 promos just split the episode in two (0:39-1:30, 1:30-2:18), long and lazy | Reading output | Judge + ranking; noted as limitation |
| Step 3 | Gemini picker | Self-scores all 23-27/30: useless for ranking | Counted score distribution | Added independent judge model |
| Step 5 | Gemini judge | Standalone score almost always 9: weak signal on that axis | Score distribution | Kept low weight (20%); noted as limitation |
| Step 5 | My ranker code | Promos the judge failed on (429) got score 0 + fake "disagree" flag | Saw E19-E39 at bottom with empty scores | Exclude unjudged promos + warning |
| Gold set | Me (human) | My starts skipped strong hooks (Ep 24 started 2.5s after the whip strike; Ep 34 began mid-trial without context) | AI critique after the blind test | Lesson: open on a physical hit or the stakes |
| Cross-check | Claude-written validator | "Move start to hook - 0.5s" put 3 starts mid-shot (E11-P1 = #3 to post, S1, S4) | Independent auditor: 76/79 | Snap to real row starts |
| Cross-check | Claude's first fix | New starts landed inside another spoken line (E11-P1, S1) | Auditor again: 77/79 | Only cut at "clean" row starts (not mid-dialogue) -> 79/79 |
| GitHub | Me | Real API key ended up in `.env.example` | GitHub push protection blocked the push | Blanked template, `git commit --amend`, re-pushed, rotated key |

## Results so far
- 50/50 episodes processed in ~5 min, ~210k tokens; 0 hallucinated line IDs.
- 81 single promos + 5 montages -> 79 usable (7 duplicates rejected, 7 auto-fixed); 11 flagged for human review.
- Gold set (human, blind): **4/5** found, each as the tool's #1 in its episode; end gap **1.4s**, start gap **13.2s**; Ep 34 missed.
- Independent audit: **79/79** promos pass 7 checks against the raw scripts; CSV rows match.
- Automated tests: **13/13** pass (parser, AI-answer handling, all validator rules, eval maths).
- Stability: re-ran Eps 3, 23, 41 -> **4/4** promos picked again with identical timestamps.
- Second judge (gpt-oss-120b, 16-promo sample): red-flag agreement **15/16**, same top pick, Spearman **0.38** (moderate) -> ranking = shortlist for an editor, not autopilot.
- Weak spots: long episodes (more good promos than it returns), quiet/visual episodes (Ep 14), hook choice.

## Entries

### [19:35] Step 0: Planning
- Read brief + 50 scripts. Chose Problem 1. Planned pipeline: parse -> AI beats -> rules -> montage -> judge -> report.

### [19:40] Step 1: Setup + key check
- Error: `zsh: unknown file attribute: q`
- Cause: pasted commands with `# comments`; zsh doesn't treat `#` as a comment interactively, read `(quotes...)` as a glob pattern.
- Fix: paste commands without comments.
- Learned: venv = separate toolbox per project; `.env` keeps secrets out of code.
- Result: paid Gemini key works; 61 models listed; chose `gemini-3.8-flash`.

### [19:48] Step 2: Parser (no AI)
- 50 episodes, 102.7 min, 1,487 dialogue / 1,754 camera / 372 action / 114 sfx lines, 0 sanity problems.
- Learned: regex patterns; sorting overlapping CAMERA/ACTION into one timeline.

### [19:52] Step 3: AI beats
- Error: `can't open file .../Kuku FM/check_key.py` + `No module named 'src'`
- Cause: terminal in `Kuku FM` (wrong folder) with a stray PyCharm venv active.
- Fix: `cd promo-finder` + `source .venv/bin/activate`; checked with `pwd` and `which python`.
- Test on 3 eps first, then all 50: 292s, 81/81 promos kept, 0 bad IDs.

### [20:05] Step 4: Validators + assembler
- Tested rules with deliberately broken clips (75s, late hook, mid-line cut, 14s, overlaps): all handled.
- Real data: 71 ok, 3 fixed, 7 duplicates rejected.

### [20:16] Step 4b + 5: Montages + judge
- Error (repeat): `No module named 'src'`. Root cause: PyCharm project opened at `Kuku FM`, it auto-created and activated its own `.venv` in every new terminal.
- Permanent fix: auto-enter rule in `~/.zshrc` + PyCharm Terminal start directory + `kuku` alias.
- Error: `RateLimitError 429` on 5 judge calls (pro model, 6 parallel workers).
- Fix: longer backoff for 429 (10/20/40/80s), 5 retries, `--workers 2`; cached results meant only 5 calls re-ran.
- Judge caught E02-P2's resolved ending independently (matches my manual note).

### [20:45] Step 6: run.py + report + evaluation
- One command runs everything; cached re-run = 0s, 0 tokens.
- Gold set built one question at a time; results above.

### [21:23] GitHub
- Error: push blocked: `GH013 Push cannot contain secrets` (`.env.example:3`).
- Cause: my real key was pasted into the template file.
- Fix: blank template, `git commit --amend --no-edit` (removes it from history), push OK. Did NOT click "allow secret". Rotated key.
- Learned: git = save points, GitHub = cloud copy; always check `git status` before the first commit; macOS keychain stored my GitHub login (`credential.helper = osxkeychain`).

### [21:40] Cross-checks (my policy: verify everything)
- Added `eval/audit.py` (independent, no src imports). First run: 76/79. Caught a real bug in the validator Claude wrote (starts at "hook - 0.5s" = mid-shot). First fix caused cuts inside another line (77/79). Final fix: only "clean" row starts -> 79/79. 0 tokens (cached results re-validated).
- Added `tests/test_core.py`: 13 tests on a made-up episode; installed pytest. 13 passed in 0.15s.
- Learned: a system checking itself can't catch its own bugs; an independent check caught two in a row.

### [21:50] Stability + second judge
- `eval/stability.py`: 3 AI calls, 4/4 promos identical on re-run -> safe to run live in the interview.
- Groq key: first run failed `GROQ_API_KEY is missing` (key not yet in .env). No Llama chat model on my Groq account -> used openai/gpt-oss-120b.
- `eval/judge_agreement.py`: 16 calls. Spearman 0.38, gap 1.7, red flags 15/16. GPT-oss is harsher; biggest disagreements E34-P1, E47-P1 (8 vs 4).
- Idea for scale: average two judges from different families; calibrate against real click-through data.
