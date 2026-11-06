"""
stitcher.py: STEP 4b. Promos that JOIN moments from different episodes.

Step 3 saved the strongest 'moments' per episode. Here we show the AI the best of them
(with a few rows of context each) in ONE call and ask for montage promos made of 2-4 segments.
Same safety net as before: the AI answers with row IDs like "E03:L071"; our code checks them,
looks up real times, and runs the same validators as single promos.

Run:  python -m src.stitcher data/raw/broken_soldier
"""
import argparse
import json
from pathlib import Path

from src.assembler import add_timestamps, load_beats
from src.beats import parse_json
from src.llm_client import USAGE, chat, current_model
from src.parser import fmt, load_show, show_key
from src.prompts import STITCH_VERSION, SYSTEM_EDITOR, stitch_prompt
from src.validators import validate

CONTEXT_ROWS = 4      # rows before/after each moment shown to the AI
MAX_MOMENTS = 45      # keeps the prompt small (~12k tokens)


def gid(ep_num, line_id):
    """Global row ID across the whole show: episode 3, L071 -> 'E03:L071'."""
    return f"E{ep_num:02d}:{line_id}"


def pick_moments(records, min_score=9):
    """Strongest moments first; ties broken by EARLIER episode (better for new viewers)."""
    moments = [m for r in records for m in r["moments"] if m.get("score", 0) >= min_score]
    moments.sort(key=lambda m: (-m["score"], m["episode"]))
    return sorted(moments[:MAX_MOMENTS], key=lambda m: (m["episode"], m["start"]))


def render_moments(moments, episodes_by_num):
    """Each moment + a few rows around it, with global row IDs."""
    blocks = []
    for m in moments:
        ep = episodes_by_num[m["episode"]]
        idx = next(i for i, r in enumerate(ep["lines"]) if r["id"] == m["line_id"])
        rows = ep["lines"][max(0, idx - CONTEXT_ROWS): idx + CONTEXT_ROWS + 1]
        lines = [f"--- Episode {m['episode']} | {m['role']} (score {m['score']}): {m['summary']}"]
        for r in rows:
            who = f"{r['speaker']} ({r['emotion']})" if r["kind"] == "dialogue" else r["kind"].upper()
            lines.append(f"{gid(m['episode'], r['id'])} [{fmt(r['start'])}-{fmt(r['end'])}] {who}: {r['text']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def resolve(row_gid, episodes_by_num):
    """'E03:L071' -> (episode_number, line dict) or None if it doesn't exist."""
    try:
        ep_part, line_id = row_gid.split(":")
        ep_num = int(ep_part.lstrip("E"))
        line = next(r for r in episodes_by_num[ep_num]["lines"] if r["id"] == line_id)
        return ep_num, line
    except (ValueError, KeyError, StopIteration, AttributeError):
        return None


def build_stitched(src, n=5, force=False):
    show = show_key(src)
    out = Path("outputs/promos") / f"{show}_stitched.json"
    episodes_by_num = {e["episode"]: e for e in load_show(src)}
    if out.exists() and not force:
        # cached montages are re-checked, so validator fixes apply without a new AI call
        result = json.loads(out.read_text())
        result["promos"] = [add_timestamps(validate(p, episodes_by_num)) for p in result["promos"]]
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        return result, out
    records = load_beats(show)
    moments = pick_moments(records)
    n = max(1, min(n, len(records) // 10))   # scale montages with show length: 2 eps -> 1, 50 eps -> 5
    premise = episodes_by_num[min(episodes_by_num)]["logline"]

    raw = chat(stitch_prompt(premise, render_moments(moments, episodes_by_num), n),
               system=SYSTEM_EDITOR, json_mode=True, temperature=0.4)
    parsed = parse_json(raw)

    promos, bad = [], 0
    for k, p in enumerate(parsed.get("promos", []), start=1):
        segs, ok = [], True
        for s in p.get("segments", []):
            a, b = resolve(s.get("start_id", ""), episodes_by_num), resolve(s.get("end_id", ""), episodes_by_num)
            if not a or not b or a[0] != b[0] or b[1]["end"] <= a[1]["start"]:
                ok = False
                break
            segs.append({"episode": a[0], "start": a[1]["start"], "end": b[1]["end"]})
        hook = resolve(p.get("hook_id", ""), episodes_by_num)
        if not ok or not segs:
            bad += 1
            continue
        hook_time = hook[1]["start"] if hook and hook[0] == segs[0]["episode"] else segs[0]["start"]
        promo = {
            "promo_id": f"S{k}", "kind": "stitched", "segments": segs, "hook_time": hook_time,
            "hook": p.get("hook", ""), "cliffhanger": p.get("cliffhanger", ""), "why": p.get("why", ""),
            "hook_type": p.get("hook_type", "other"), "ai_scores": {}, "ai_score": 0,
        }
        promos.append(add_timestamps(validate(promo, episodes_by_num)))

    result = {"model": current_model(), "prompt_version": STITCH_VERSION,
              "moments_shown": len(moments), "bad_ids": bad, "promos": promos, "raw_response": raw}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return result, out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Step 4b: montage promos across episodes")
    ap.add_argument("src")
    ap.add_argument("--n", type=int, default=5, help="how many montage promos to ask for")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    result, out = build_stitched(args.src, n=args.n, force=args.force)

    print(f"Moments shown to AI: {result['moments_shown']} | invalid promos dropped: {result['bad_ids']}")
    for p in result["promos"]:
        segs = " + ".join(f"Ep{s['episode']} {s['start_ts']}-{s['end_ts']}" for s in p["segments"])
        print(f"  {p['promo_id']} [{p['status']}] {p['duration']}s: {segs}  {p['flags']}")
        print(f"      hook: {p['hook'][:90]}")
    print(f"Tokens: {USAGE}\nSaved -> {out}")