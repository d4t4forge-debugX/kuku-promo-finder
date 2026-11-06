"""
report.py: turns the ranked promos into files a human editor can use.

Writes to outputs/final/:
  <show>_promos.csv   one row per promo (open in Excel / Google Sheets)
  <show>_report.md    the readable summary: what to post first, what to review, what was rejected

Two lists (decision C):
  ACQUISITION  promos from early episodes (<= ACQ_MAX_EP). A new viewer who taps lands on Ep 1,
               so the clip should match what they are about to watch. Post these first.
  BEST OVERALL every judged promo by score (late episodes too), e.g. for retargeting existing viewers.

Run:  python -m src.report data/raw/broken_soldier
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from src.ranker import posting_order

ACQ_MAX_EP = 15


def seg_text(p):
    return " + ".join(f"Ep{s['episode']} {s['start_ts']}-{s['end_ts']}" for s in p["segments"])


def acquisition_list(ranked, top_n=8):
    clean = [p for p in ranked
             if max(s["episode"] for s in p["segments"]) <= ACQ_MAX_EP and not p["review_reasons"]]
    return posting_order(clean, top_n=top_n)


def write_csv(ranked, path):
    cols = ["rank", "promo_id", "kind", "segments", "duration", "final_score",
            "judge_hook", "judge_cliffhanger", "judge_standalone", "judge_overall",
            "hook", "cliffhanger", "why", "hook_type", "judge_verdict", "judge_fix",
            "flags", "needs_review"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for p in ranked:
            j = p.get("judge", {})
            w.writerow({
                "rank": p["rank"], "promo_id": p["promo_id"], "kind": p["kind"],
                "segments": seg_text(p), "duration": p["duration"], "final_score": p["final_score"],
                "judge_hook": j.get("hook"), "judge_cliffhanger": j.get("cliffhanger"),
                "judge_standalone": j.get("standalone"), "judge_overall": j.get("overall"),
                "hook": p["hook"], "cliffhanger": p["cliffhanger"], "why": p["why"],
                "hook_type": p["hook_type"], "judge_verdict": j.get("one_line_verdict", ""),
                "judge_fix": j.get("fix", ""), "flags": "; ".join(p["flags"]),
                "needs_review": "; ".join(p["review_reasons"]),
            })


def promo_block(n, p):
    j = p.get("judge", {})
    return (f"### {n}. {p['promo_id']} ({p['kind']}, {p['duration']}s, score {p['final_score']})\n"
            f"- **Segments:** {seg_text(p)}\n"
            f"- **Hook (first 3s):** {p['hook']}\n"
            f"- **Cliffhanger:** {p['cliffhanger']}\n"
            f"- **Why it works:** {p['why']}\n"
            f"- **Judge:** hook {j.get('hook')} / cliffhanger {j.get('cliffhanger')} / "
            f"standalone {j.get('standalone')} / overall {j.get('overall')}: {j.get('one_line_verdict', '')}\n"
            + (f"- **Suggested fix:** {j['fix']}\n" if j.get("fix") else ""))


def write_report(src):
    show = Path(src).stem
    final = Path("outputs/final")
    data = json.loads((final / f"{show}_ranked.json").read_text())
    ranked = data["ranked"]

    all_promos = json.loads((Path("outputs/promos") / f"{show}_single.json").read_text())
    stitched_file = Path("outputs/promos") / f"{show}_stitched.json"
    if stitched_file.exists():
        all_promos += json.loads(stitched_file.read_text())["promos"]
    rejected = [p for p in all_promos if p["status"] == "rejected"]

    acq = acquisition_list(ranked)
    review = [p for p in ranked if p["review_reasons"]]
    status = Counter(p["status"] for p in all_promos)

    md = [f"# Promo report: {show}\n",
          f"Judge model: `{data['judge_model']}` | promos found: {len(all_promos)} "
          f"(ok {status.get('ok', 0)}, auto-fixed {status.get('fixed', 0)}, rejected {status.get('rejected', 0)}) "
          f"| judged & ranked: {len(ranked)} | need human review: {len(review)}\n",
          f"## 1. Post first: acquisition list (episodes 1-{ACQ_MAX_EP}, no review flags)\n",
          "New viewers who tap a promo start at Episode 1, so these clips match what they are about to watch. "
          "Order avoids repeating the same episode or hook type back-to-back.\n"]
    md += [promo_block(i, p) for i, p in enumerate(acq, 1)]
    md += ["\n## 2. Best overall (all episodes, by score)\n",
           "| # | Promo | Segments | Sec | Score | Hook type | Review |", "|---|---|---|---|---|---|---|"]
    md += [f"| {p['rank']} | {p['promo_id']} | {seg_text(p)} | {p['duration']} | {p['final_score']} | "
           f"{p['hook_type']} | {', '.join(p['review_reasons'])} |" for p in ranked[:15]]
    md += ["\n## 3. Needs a human look\n"]
    md += [f"- **{p['promo_id']}** ({seg_text(p)}): {', '.join(p['review_reasons'])}. "
           f"Judge: {p.get('judge', {}).get('one_line_verdict', '')}" for p in review] or ["- none"]
    md += ["\n## 4. Rejected by the rule checks\n"]
    md += [f"- **{p['promo_id']}** ({seg_text(p)}): {', '.join(p['flags'])}" for p in rejected] or ["- none"]

    (final / f"{show}_report.md").write_text("\n".join(md), encoding="utf-8")
    write_csv(ranked, final / f"{show}_promos.csv")
    return acq, final / f"{show}_report.md", final / f"{show}_promos.csv"


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "data/raw/broken_soldier"
    acq, md_path, csv_path = write_report(src)
    print("ACQUISITION POSTING ORDER:")
    for i, p in enumerate(acq, 1):
        print(f"  {i}. {p['promo_id']:<7} {seg_text(p)} ({p['duration']}s, score {p['final_score']}, {p['hook_type']})")
    print(f"\nSaved -> {md_path}\nSaved -> {csv_path}")