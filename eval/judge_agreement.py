"""
judge_agreement.py: does a judge from a DIFFERENT AI family agree with our main judge?

Why: Gemini picks the clips AND Gemini judges them, so they might share the same taste.
A second judge from another company (e.g. Llama on Groq) scores a fixed sample of promos
with the SAME prompt. If the two judges rank promos similarly, the ranking is not just
one model's opinion.

Sample: every 5th promo in the current ranking (fixed rule -> top, middle and bottom included).
Metrics:
  Spearman rank correlation of 'overall' scores (-1..1; above ~0.5 = clear agreement)
  average absolute score gap
  agreement on the 'resolved_inside' red flag

Run:  python -m eval.judge_agreement data/raw/broken_soldier --provider groq --model llama-3.3-70b-versatile
"""
import argparse
import json
from pathlib import Path

from src.beats import parse_json
from src.llm_client import USAGE, chat
from src.parser import load_show
from src.prompts import SYSTEM_JUDGE, judge_prompt
from src.ranker import render_clip


def ranks(values):
    """Rank values (average rank for ties): [10, 20, 20] -> [1, 2.5, 2.5]."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    r = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(x, y):
    """Spearman correlation = Pearson correlation of the ranks."""
    rx, ry = ranks(x), ranks(y)
    n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy) if vx and vy else 0.0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--provider", default="groq")
    ap.add_argument("--model", default="llama-3.3-70b-versatile")
    ap.add_argument("--every", type=int, default=5, help="take every Nth promo of the ranking")
    args = ap.parse_args()

    show = Path(args.src).stem
    episodes = {e["episode"]: e for e in load_show(args.src)}
    ranked = json.loads((Path("outputs/final") / f"{show}_ranked.json").read_text())["ranked"]
    sample = ranked[::args.every]
    cache = Path("outputs/judge2") / show / args.model.replace("/", "_")
    cache.mkdir(parents=True, exist_ok=True)

    main_scores, second_scores, flag_agree, rows = [], [], 0, []
    for p in sample:
        path = cache / f"{p['promo_id']}.json"
        if path.exists():
            v = json.loads(path.read_text())
        else:
            raw = chat(judge_prompt(render_clip(p, episodes)), system=SYSTEM_JUDGE,
                       provider=args.provider, model=args.model, json_mode=True, temperature=0.0)
            v = parse_json(raw)
            path.write_text(json.dumps(v, indent=2, ensure_ascii=False))
        a, b = float(p["judge"].get("overall", 0)), float(v.get("overall", 0) or 0)
        main_scores.append(a)
        second_scores.append(b)
        same_flag = bool(p["judge"].get("resolved_inside")) == bool(v.get("resolved_inside"))
        flag_agree += same_flag
        rows.append(f"| {p['rank']} | {p['promo_id']} | {a:.0f} | {b:.0f} | "
                    f"{'yes' if same_flag else 'NO'} |")

    rho = spearman(main_scores, second_scores)
    gap = sum(abs(a - b) for a, b in zip(main_scores, second_scores)) / len(sample)
    lines = [f"# Judge agreement: {show}", "",
             f"Main judge: `{json.loads((Path('outputs/final') / f'{show}_ranked.json').read_text())['judge_model']}` | "
             f"Second judge: `{args.provider}/{args.model}` | sample: every {args.every}th promo ({len(sample)} promos)", "",
             "| Main rank | Promo | Main overall | Second overall | Same 'resolved' flag? |", "|---|---|---|---|---|"]
    lines += rows
    lines += ["", f"**Spearman rank correlation:** {rho:.2f} | **avg score gap:** {gap:.1f} points | "
                  f"**red-flag agreement:** {flag_agree}/{len(sample)}"]
    out = Path("outputs/final") / f"{show}_judge_agreement.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nTokens: {USAGE}\nSaved -> {out}")