"""
assembler.py: STEP 4. Turn the AI's raw picks into clean, rule-checked promos.

Reads the cached beats (Step 3), converts every pick into one shared format
(a promo = a list of segments, so single clips and multi-episode stitches look the same),
runs validators, removes duplicates, and saves outputs/promos/<show>_single.json.

Run:  python -m src.assembler data/raw/broken_soldier
"""
import json
import sys
from collections import Counter
from pathlib import Path

from src.parser import fmt, load_show
from src.validators import dedupe, validate


def load_beats(show):
    folder = Path("outputs/beats") / show
    records = [json.loads(f.read_text()) for f in sorted(folder.glob("ep_*.json"))]
    if not records:
        raise FileNotFoundError(f"No beats in {folder}. Run Step 3 (src.beats) first.")
    return records


def to_promo(p, n):
    """One AI pick -> shared promo format."""
    ai_score = p.get("hook_score", 0) + p.get("cliffhanger_score", 0) + p.get("standalone_score", 0)
    return {
        "promo_id": f"E{p['episode']:02d}-P{n}",
        "kind": "single",
        "segments": [{"episode": p["episode"], "start": p["start"], "end": p["end"]}],
        "hook_time": p["hook_time"],
        "hook": p.get("hook", ""), "cliffhanger": p.get("cliffhanger", ""), "why": p.get("why", ""),
        "hook_type": p.get("hook_type", "other"),
        "ai_scores": {k: p.get(k, 0) for k in ("hook_score", "cliffhanger_score", "standalone_score")},
        "ai_score": ai_score,          # 3..30, the generator's own opinion (judged again in Step 5)
    }


def add_timestamps(promo):
    """Human-readable mm:ss.cc for every segment."""
    for s in promo["segments"]:
        s["start_ts"], s["end_ts"] = fmt(s["start"]), fmt(s["end"])
    return promo


def build_single_promos(src):
    show = Path(src).stem
    episodes_by_num = {e["episode"]: e for e in load_show(src)}
    records = load_beats(show)

    promos = []
    for rec in records:
        for n, p in enumerate(rec["promos"], start=1):
            promos.append(validate(to_promo(p, n), episodes_by_num))
    promos = dedupe(promos)
    promos = [add_timestamps(p) for p in promos]

    out = Path("outputs/promos") / f"{show}_single.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(promos, indent=2, ensure_ascii=False))
    return promos, out


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "data/raw/broken_soldier"
    promos, out = build_single_promos(src)

    print(f"{len(promos)} promos from the AI")
    print("Status:", dict(Counter(p["status"] for p in promos)))
    print("Flags :", dict(Counter(f.split("_of_")[0] for p in promos for f in p["flags"])))
    durs = [p["duration"] for p in promos if p["status"] != "rejected"]
    if durs:
        print(f"Length of usable promos: min {min(durs)}s, avg {sum(durs) / len(durs):.1f}s, max {max(durs)}s")
    print("\nSample:")
    for p in promos[:6]:
        s = p["segments"][0]
        print(f"  {p['promo_id']} [{p['status']:8}] Ep{s['episode']} {s['start_ts']}-{s['end_ts']} "
              f"({p['duration']}s, hook@+{p['hook_offset']}s) {p['flags']}")
    print(f"\nSaved -> {out}")