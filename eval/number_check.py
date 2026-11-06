# Read-only number check: prints every number the solution doc relies on, straight from the output files.
# Run from promo-finder:  python eval/number_check.py
import json, glob, re
from collections import Counter

S = "broken_soldier"
F = "outputs/final"

print("== 1. Parsed scripts ==")
eps = json.load(open(f"outputs/parsed/{S}.json"))
print("episodes:", len(eps))
print("total minutes:", round(sum(e["duration"] for e in eps) / 60, 1))

print("\n== 2. Picker (beats) ==")
beats = [json.load(open(f)) for f in sorted(glob.glob(f"outputs/beats/{S}/ep_*.json"))]
print("episode files:", len(beats), "| parse errors:", sum(1 for b in beats if b.get("parse_error")))
print("bad_ids total:", sum(b["report"]["bad_ids"] for b in beats),
      "| bad_order total:", sum(b["report"]["bad_order"] for b in beats))
print("promos proposed:", sum(b["report"]["promos_in"] for b in beats),
      "| kept:", sum(b["report"]["promos_kept"] for b in beats))
self_scores = [x["hook_score"] + x["cliffhanger_score"] + x["standalone_score"] for b in beats for x in b["promos"]]
print("picker self-score /30: min", min(self_scores), "max", max(self_scores),
      "| share in 23-27:", sum(23 <= s <= 27 for s in self_scores), "/", len(self_scores))

print("\n== 3. Validators ==")
single = json.load(open(f"outputs/promos/{S}_single.json"))
stitched_file = json.load(open(f"outputs/promos/{S}_stitched.json"))
stitched = stitched_file["promos"]
print("montage bad_ids:", stitched_file["bad_ids"])
print("single promos:", len(single), dict(Counter(p["status"] for p in single)))
print("montages:", len(stitched), dict(Counter(p["status"] for p in stitched)))

print("\n== 4. Judge + ranking ==")
r = json.load(open(f"{F}/{S}_ranked.json"))
ranked = r["ranked"]
print("ranked (usable):", len(ranked))
print("need review:", sum(1 for p in ranked if p["review_reasons"]))
print("review reasons:", dict(Counter(x for p in ranked for x in p["review_reasons"])))
ov = [p["judge"]["overall"] for p in ranked]
print("judge overall: min", min(ov), "max", max(ov))
print("resolved_inside:", sum(p["judge"]["resolved_inside"] for p in ranked),
      "| confusing:", sum(p["judge"]["confusing"] for p in ranked))
st = [p["judge"]["standalone"] for p in ranked]
print("standalone scores:", dict(sorted(Counter(st).items())))
print("judge cache files:", len(glob.glob(f"outputs/judge/{S}/*.json")))
print("episodes with no promo:", sorted(set(range(1, 51)) - {s["episode"] for p in ranked for s in p["segments"]}))

print("\n== 5. Post-first (acquisition) list, from the report ==")
rep = open(f"{F}/{S}_report.md").read()
print(rep[:1500])

print("\n== 6. Quality files (exact lines) ==")
for name, pat in [("audit", r"passing all|passed"), ("eval_gold_set", r"Hit rate"),
                  ("stability", r"picked again"), ("judge_agreement", r"Spearman")]:
    for line in open(f"{F}/{S}_{name}.md"):
        if re.search(pat, line):
            print(f"{name}: {line.strip()}")
