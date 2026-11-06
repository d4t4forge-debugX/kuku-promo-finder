"""
evaluate.py: compares the tool's promos against promos picked by hand (a "gold set").

Two gold sets, two perspectives:
  eval/gold_set.json             HUMAN, BLIND: picked by Rohit before seeing tool output.
                                 This is the only one reported as accuracy.
  eval/gold_set_v2_revised.json  AI-ASSISTED, NOT BLIND: Rohit's picks revised after an AI critique.
                                 A learning example, not evidence.

Episodes 4, 14, 24, 34, 44 were chosen by a fixed rule (every 10th) so nobody cherry-picked easy ones.

Metrics:
  hit           the tool has a usable promo covering >= 50% of the gold clip
  start/end gap how many seconds the tool's cut points are from the gold ones
  top_match     the tool's highest-scored promo in that episode is the one that matches

Run:
  python -m eval.evaluate data/raw/broken_soldier                                   # human blind set
  python -m eval.evaluate data/raw/broken_soldier eval/gold_set_v2_revised.json     # AI-assisted set
"""
import json
import sys
from pathlib import Path

GOLD = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("eval/gold_set.json")


def secs(ts):
    """'01:24.00' -> 84.0"""
    m, s = ts.split(":")
    return int(m) * 60 + float(s)


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def evaluate(src):
    show = Path(src).stem
    gold = json.loads(GOLD.read_text())
    ranked = json.loads((Path("outputs/final") / f"{show}_ranked.json").read_text())["ranked"]
    singles = [p for p in ranked if p["kind"] == "single"]

    rows = []
    for g in gold["promos"]:
        if not g.get("start") or not g.get("end"):
            print(f"  skipping Ep {g['episode']}: start/end not filled in")
            continue
        g0, g1 = secs(g["start"]), secs(g["end"])
        if g1 <= g0:
            print(f"  skipping Ep {g['episode']}: end is not after start")
            continue
        cands = [p for p in singles if p["segments"][0]["episode"] == g["episode"]]
        best, best_cov = None, 0.0
        for p in cands:
            s = p["segments"][0]
            cov = overlap(g0, g1, s["start"], s["end"]) / (g1 - g0)
            if cov > best_cov:
                best, best_cov = p, cov
        top = max(cands, key=lambda p: p["final_score"]) if cands else None
        row = {"episode": g["episode"], "gold": f"{g['start']}-{g['end']}",
               "tool_promos_in_ep": len(cands), "coverage": round(best_cov, 2), "hit": best_cov >= 0.5}
        if best:
            s = best["segments"][0]
            row.update({"tool": f"{s['start_ts']}-{s['end_ts']} ({best['promo_id']})",
                        "start_gap": round(abs(s["start"] - g0), 1), "end_gap": round(abs(s["end"] - g1), 1),
                        "top_match": top is best})
        rows.append(row)
    return gold, rows


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "data/raw/broken_soldier"
    gold, rows = evaluate(src)
    if not rows:
        sys.exit(f"Gold set {GOLD} is empty: fill it in first.")

    hits = [r for r in rows if r["hit"]]
    lines = [f"# Gold-set evaluation: {GOLD.name}\n",
             f"**Annotator:** {gold.get('annotator', '?')}  ",
             f"**Method:** {gold.get('method', '')}\n",
             "| Ep | Gold pick | Closest tool promo | Coverage | Hit | Start gap (s) | End gap (s) | Tool's #1 in ep? |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['episode']} | {r['gold']} | {r.get('tool', 'none')} | {r['coverage']} | "
                     f"{'yes' if r['hit'] else 'NO'} | {r.get('start_gap', '-')} | {r.get('end_gap', '-')} | "
                     f"{'yes' if r.get('top_match') else 'no'} |")
    summary = (f"\n**Hit rate:** {len(hits)}/{len(rows)} gold picks found by the tool"
               + (f" | **avg start gap:** {sum(r['start_gap'] for r in hits) / len(hits):.1f}s"
                  f" | **avg end gap:** {sum(r['end_gap'] for r in hits) / len(hits):.1f}s" if hits else ""))
    lines.append(summary)

    out = Path("outputs/final") / f"{Path(src).stem}_eval_{GOLD.stem}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nSaved -> {out}")