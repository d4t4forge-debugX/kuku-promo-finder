"""
stability.py: if we run the AI picker TWICE on the same episode, does it pick the same clips?

Why: Kuku will run the tool live in the interview. If every run gives totally different promos,
the tool is a slot machine, not a tool. Temperature is 0.2 (low randomness), but not 0.

How: re-runs the picker on a few FIXED episodes into a separate folder (outputs/stability/),
never touching the main cache, then matches each original promo to the closest new one.
"Same clip" = they overlap by >= 50% of the shorter clip.

Run:  python -m eval.stability data/raw/broken_soldier          (3 AI calls)
"""
import json
import sys
from pathlib import Path

from src.beats import extract_episode
from src.llm_client import USAGE
from src.parser import load_show

EPISODES = [3, 23, 41]     # fixed rule: one early, one middle, one late episode


def overlap_share(a, b):
    inter = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    shorter = min(a["end"] - a["start"], b["end"] - b["start"])
    return inter / max(shorter, 0.01)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "data/raw/broken_soldier"
    show = Path(src).stem
    episodes = {e["episode"]: e for e in load_show(src)}
    premise = episodes[min(episodes)]["logline"]
    rerun_dir = Path("outputs/stability") / show
    rerun_dir.mkdir(parents=True, exist_ok=True)

    rows, matched_total, original_total = [], 0, 0
    for n in EPISODES:
        original = json.loads((Path("outputs/beats") / show / f"ep_{n:03d}.json").read_text())["promos"]
        rerun, _ = extract_episode(episodes[n], premise, rerun_dir, force=True)
        new = rerun["promos"]
        for p in original:
            best = max(new, key=lambda q: overlap_share(p, q), default=None)
            share = overlap_share(p, best) if best else 0.0
            same = share >= 0.5
            matched_total += same
            original_total += 1
            rows.append(f"| {n} | {p['start_ts']}-{p['end_ts']} | "
                        f"{(best['start_ts'] + '-' + best['end_ts']) if best else 'none'} | "
                        f"{share:.2f} | {'yes' if same else 'NO'} |")
        rows.append(f"| {n} | ({len(original)} promos first run) | ({len(new)} promos second run) | | |")

    lines = [f"# Stability check: {show}", "",
             f"Episodes re-run (fixed): {EPISODES} | same model, same prompt, temperature 0.2", "",
             "| Ep | First run | Closest in second run | Overlap | Same clip? |", "|---|---|---|---|---|"]
    lines += rows
    lines += ["", f"**{matched_total}/{original_total} first-run promos were picked again** on the second run."]
    out = Path("outputs/final") / f"{show}_stability.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nTokens: {USAGE}\nSaved -> {out}")