# Promo Finder: Kuku AI Generalist Assignment (Problem 1)

Reads a microdrama screenplay (one .txt per episode, timestamped) and finds the best
20-60 second promo clips: **hook in the first 3 seconds, ends on a cliffhanger, makes sense alone**.
Outputs exact episode + start/end timestamps, the hook, the cliffhanger, a reason, and a ranked posting order.

## How it works
```
scripts ──► 1. parser (code)          every line -> {id, start, end, speaker, emotion, text}
        ──► 2. beats (AI, per episode) picks promos + key moments, answering ONLY with line IDs
        ──► 3. validators (code)       20-60s, hook within 3s, no mid-line cuts, de-duplicate
        ──► 4. stitcher (AI)           montage promos joining moments across episodes
        ──► 5. judge (different AI)    scores each clip as a stranger would see it
        ──► 6. report (code)           CSV + Markdown: what to post first, what needs a human look
```
**Design choices**
- **The AI never writes timestamps.** It answers with line IDs (`L012`); code looks up the times, so made-up timestamps can't happen.
- **Rules live in code, taste lives in AI.** Length, the 3-second hook and clean cuts are enforced in `validators.py`.
- **A separate judge model.** The picker's self-scores barely vary (23-27/30), so a different model judges each clip blind.
- **Any model, one setting.** Every provider is called through the OpenAI-compatible API; change `LLM_MODEL` / `JUDGE_MODEL` in `.env`.
- **Cached and resumable.** Every AI result is saved per episode; re-runs only pay for what's missing.

## Run it
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add your API key + model names
python check_key.py             # confirms the key and lists models
python run.py path/to/show      # folder of episode .txt files, or a .zip
```
Outputs land in `outputs/final/`: `<show>_report.md` (start here), `<show>_promos.csv`, `<show>_ranked.json`.

**Swap models**, e.g. `LLM_PROVIDER=openai`, `LLM_MODEL=...`, or `JUDGE_MODEL=...` in `.env`.
Supported providers: gemini, groq, openai, anthropic.

## Quality check
- `python -m eval.evaluate <show>` compares the tool against a **blind human gold set** (`eval/gold_set.json`, 5 episodes chosen by a fixed rule).
- Result on the input pack: **4/5** human picks found, each as the tool's #1 for that episode; end points within **1.4s** on average, start points 13.2s apart.
- `eval/gold_set_v2_revised.json` is an AI-assisted, **not blind** revision, kept separately as a learning example and not reported as accuracy.

## Known limits
- Reads text only: purely visual hooks (a look, a silent gesture) are under-rated and flagged `mostly_visual`.
- Long episodes (3 min+) can hold more good promos than the 2-3 it returns.
- Script timestamps are assumed to match the final edit.
- The gold set is one non-expert annotator on 5 episodes: a sanity check, not proof.

## Repo layout
`src/` pipeline · `eval/` gold sets + evaluator · `run.py` one-command pipeline · `JOURNEY_LOG.md` build log, errors and decisions.
The input scripts are Kuku's confidential content and are **not** in this repo (`data/raw/` is git-ignored).