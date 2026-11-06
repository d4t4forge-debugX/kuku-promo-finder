"""
show_episode.py: print one episode as a compact, readable timeline (no CAMERA rows).
Used for making the gold set by hand.

Run:  python -m eval.show_episode 4
"""
import sys

from src.parser import fmt, load_show

ep_num = int(sys.argv[1])
src = sys.argv[2] if len(sys.argv) > 2 else "data/raw/broken_soldier"
ep = next(e for e in load_show(src) if e["episode"] == ep_num)

print(f"EPISODE {ep_num} ({ep['duration']:.0f}s): {ep['logline']}\n")
for r in ep["lines"]:
    if r["kind"] == "camera":
        continue
    who = f"{r['speaker']} ({r['emotion']})" if r["kind"] == "dialogue" else r["kind"].upper()
    print(f"{fmt(r['start'])}-{fmt(r['end'])}  {who}: {r['text']}")