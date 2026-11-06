"""
ranker.py: STEP 5. An independent JUDGE scores every promo, then code ranks them.

Why a separate judge?
  The model that picked a clip is biased toward its own pick (its self-scores barely vary).
  So a DIFFERENT model (JUDGE_MODEL in .env) watches ONLY the clip, like a stranger on TikTok,
  and scores it. Judging is cached per promo in outputs/judge/<show>/.

Final score = weighted judge scores + small rule-based adjustments (all visible in 'score_parts').
Posting order = best score first, but avoid repeating the same episode/hook type back-to-back.

Run:  python -m src.ranker data/raw/broken_soldier
"""
import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.beats import parse_json
from src.llm_client import USAGE, chat, current_model
from src.parser import load_show, show_key
from src.prompts import JUDGE_VERSION, PROMPT_VERSION, STITCH_VERSION, SYSTEM_JUDGE, judge_prompt

WEIGHTS = {"hook": 0.35, "cliffhanger": 0.30, "standalone": 0.20, "overall": 0.15}
EARLY_UNTIL_EP = 10      # promos starting at or before this episode get the funnel bonus
SPOILER_FROM_EP = 31     # promos starting at or after this episode get the spoiler-risk penalty


def judge_model():
    return os.getenv("JUDGE_MODEL") or os.getenv("LLM_MODEL")


def render_clip(promo, episodes_by_num):
    """The promo exactly as a viewer sees it: rows inside each segment, time relative to clip start."""
    out, offset = [], 0.0
    for n, seg in enumerate(promo["segments"], start=1):
        if len(promo["segments"]) > 1:
            out.append(f"--- CUT TO segment {n} ---")
        for r in episodes_by_num[seg["episode"]]["lines"]:
            if r["start"] >= seg["start"] - 0.01 and r["start"] < seg["end"]:
                t = offset + (r["start"] - seg["start"])
                who = f"{r['speaker']} ({r['emotion']})" if r["kind"] == "dialogue" else r["kind"].upper()
                out.append(f"[+{t:.1f}s] {who}: {r['text']}")
        offset += seg["end"] - seg["start"]
    return "\n".join(out)


def judge_one(promo, episodes_by_num, cache_dir, force=False):
    path = cache_dir / f"{promo['promo_id']}.json"
    if path.exists() and not force:
        return json.loads(path.read_text())
    raw = chat(judge_prompt(render_clip(promo, episodes_by_num)), system=SYSTEM_JUDGE,
               model=judge_model(), json_mode=True, temperature=0.0)
    try:
        verdict, error = parse_json(raw), None
    except Exception as e:
        verdict, error = {}, f"{type(e).__name__}: {e}"
    rec = {"promo_id": promo["promo_id"], "model": judge_model(), "prompt_version": JUDGE_VERSION,
           "verdict": verdict, "parse_error": error, "raw_response": raw}
    path.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    return rec


def final_score(promo, v):
    """0-10 score. Every adjustment is stored so you can explain any rank in the interview."""
    parts = {k: round(WEIGHTS[k] * float(v.get(k, 0) or 0), 2) for k in WEIGHTS}
    first_ep = promo["segments"][0]["episode"]
    adj = {}
    if "ends_on_episode_ending" in promo["flags"]:
        adj["ends_on_writer_cliffhanger"] = +0.3
    if first_ep <= EARLY_UNTIL_EP:
        adj["early_episode_funnel"] = +0.3      # viewer who taps lands on Ep 1: early clips match what they'll watch
    elif first_ep >= SPOILER_FROM_EP:
        adj["late_episode_spoiler_risk"] = -0.3
    if v.get("resolved_inside"):
        adj["resolved_inside_clip"] = -1.0
    if v.get("confusing"):
        adj["confusing_for_stranger"] = -0.7
    if any(f.startswith("trimmed_end") for f in promo["flags"]):
        adj["trimmed_end"] = -0.3
    if "mostly_visual_text_only_judgement_weak" in promo["flags"]:
        adj["low_confidence_visual"] = -0.2
    score = sum(parts.values()) + sum(adj.values())
    return round(max(0.0, min(10.0, score)), 2), {**parts, **adj}


def needs_review(promo, v):
    """Flag disagreement between the picker (self-score) and the judge, or judge red flags."""
    reasons = []
    if promo["ai_score"]:
        self_avg = promo["ai_score"] / 3
        if abs(self_avg - float(v.get("overall", 0) or 0)) >= 3:
            reasons.append("picker_and_judge_disagree")
    if v.get("resolved_inside"):
        reasons.append("ending_resolves_question")
    if v.get("confusing"):
        reasons.append("may_confuse_strangers")
    return reasons


def posting_order(ranked, top_n=10):
    """Greedy: take the best remaining promo, but skip one that repeats the last pick's episode or hook type."""
    pool, order = list(ranked), []
    while pool and len(order) < top_n:
        last = order[-1] if order else None
        pick = next((p for p in pool if not last or (
            p["segments"][0]["episode"] != last["segments"][0]["episode"]
            and p["hook_type"] != last["hook_type"])), pool[0])
        order.append(pick)
        pool.remove(pick)
    return order


def rank_show(src, workers=6, force=False):
    show = show_key(src)
    episodes_by_num = {e["episode"]: e for e in load_show(src)}
    folder = Path("outputs/promos")
    promos = json.loads((folder / f"{show}_single.json").read_text())
    stitched_file = folder / f"{show}_stitched.json"
    if stitched_file.exists():
        promos += json.loads(stitched_file.read_text())["promos"]
    usable = [p for p in promos if p["status"] != "rejected"]

    cache_dir = Path("outputs/judge") / show
    cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"Judge model: {judge_model()} | {len(usable)} usable promos (of {len(promos)})")

    verdicts = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(judge_one, p, episodes_by_num, cache_dir, force): p["promo_id"] for p in usable}
        for fut in as_completed(futures):
            pid = futures[fut]
            try:
                verdicts[pid] = fut.result()
            except Exception as e:
                print(f"  {pid}: judge FAILED -> {type(e).__name__}: {e}")

    judged, unjudged = [], []
    for p in usable:
        v = (verdicts.get(p["promo_id"], {}) or {}).get("verdict") or {}
        if not v:                       # judge failed -> don't pretend it scored 0
            unjudged.append(p["promo_id"])
            continue
        p["judge"] = v
        p["final_score"], p["score_parts"] = final_score(p, v)
        p["review_reasons"] = needs_review(p, v)
        p["spoiler_risk"] = p["segments"][0]["episode"] >= SPOILER_FROM_EP
        judged.append(p)
    if unjudged:
        print(f"WARNING: {len(unjudged)} promos not judged (re-run to retry): {unjudged}")

    ranked = sorted(judged, key=lambda p: p["final_score"], reverse=True)
    for i, p in enumerate(ranked, start=1):
        p["rank"] = i
    order = posting_order(ranked)
    for i, p in enumerate(order, start=1):
        p["post_order"] = i

    out = Path("outputs/final") / f"{show}_ranked.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "show": show, "source": Path(src).stem,
        "picker_model": current_model(), "judge_model": judge_model(),
        "prompt_versions": [PROMPT_VERSION, STITCH_VERSION, JUDGE_VERSION],
        "episodes": {str(n): ep["duration"] for n, ep in sorted(episodes_by_num.items())},
        "ranked": ranked, "posting_order": [p["promo_id"] for p in order],
    }, indent=2, ensure_ascii=False))
    return ranked, order, out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Step 5: independent judge + final ranking")
    ap.add_argument("src")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    ranked, order, out = rank_show(args.src, workers=args.workers, force=args.force)

    print("\nTOP 10 BY SCORE")
    for p in ranked[:10]:
        segs = " + ".join(f"Ep{s['episode']} {s['start_ts']}-{s['end_ts']}" for s in p["segments"])
        j = p["judge"]
        print(f"  #{p['rank']:<2} {p['final_score']:>5}  {p['promo_id']:<7} {segs} ({p['duration']}s) "
              f"H{j.get('hook')} C{j.get('cliffhanger')} S{j.get('standalone')} O{j.get('overall')} {p['review_reasons']}")
    print("\nPOSTING ORDER:", " -> ".join(p["promo_id"] for p in order))
    flagged = sum(1 for p in ranked if p["review_reasons"])
    print(f"Needs human review: {flagged}/{len(ranked)}")
    print(f"Tokens: {USAGE}\nSaved -> {out}")