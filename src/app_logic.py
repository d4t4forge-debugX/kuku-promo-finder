"""
app_logic.py: everything the app CALCULATES, kept out of app.py.

app.py only draws the screen; this file decides what to show. Keeping them apart means
these functions can be tested with pytest, without a browser (tests/test_app_logic.py).
"""
import csv
import io
import json
import re
import tempfile
from pathlib import Path

from src.parser import fmt, timecode
from src.report import acquisition_list, timecode_text, write_timecode_csv

FILTERS = ["Post first", "All", "Needs review", "Montages", "Approved", "Rejected"]
REJECT_REASONS = ["Cliffhanger already resolved", "Needs context / confusing", "Weak hook",
                  "Spoiler", "Too slow / too long", "Other"]
QUALITY_FOLDERS = [Path("outputs/final"), Path("docs/quality")]   # local results first, then the committed copies


# ------------------------------------------------------------------ runs
RUN_FOLDERS = (Path("outputs/final"), Path("demo/final"))   # local runs first, then the committed made-up demo


def find_runs(folders=RUN_FOLDERS):
    """Finished runs: every <show>_ranked.json in the local outputs, then the bundled demo."""
    if isinstance(folders, Path):
        folders = (folders,)
    return [r for f in folders if f.exists() for r in sorted(f.glob("*_ranked.json"))]


def episode_numbers(data):
    """All episode numbers of the show (from ranked.json), falling back to the ones promos use."""
    if data.get("episodes"):
        return sorted(int(k) for k in data["episodes"])
    return sorted({s["episode"] for p in data["ranked"] for s in p["segments"]})


# ------------------------------------------------------------------ editor decisions
def status_of(pid, decisions):
    return decisions.get(pid, {}).get("status", "")


def acquisition_ids(ranked):
    return [p["promo_id"] for p in acquisition_list(ranked)]


def filter_promos(ranked, name, decisions):
    """The promos a filter chip shows, in the right order."""
    if name == "Post first":
        return acquisition_list(ranked)
    if name == "Needs review":
        return [p for p in ranked if p["review_reasons"]]
    if name == "Montages":
        return [p for p in ranked if p["kind"] == "stitched"]
    if name == "Approved":
        return [p for p in ranked if status_of(p["promo_id"], decisions) == "approved"]
    if name == "Rejected":
        return [p for p in ranked if status_of(p["promo_id"], decisions) == "rejected"]
    return list(ranked)


def table_rows(promos, decisions):
    """One row per promo for the table: episode, timecodes in/out, score, hook, flags, decision."""
    rows = []
    for p in promos:
        eps = [s["episode"] for s in p["segments"]]
        rows.append({
            "#": p["rank"], "Promo": p["promo_id"],
            "Ep": str(eps[0]) if len(eps) == 1 else " → ".join(str(e) for e in eps),
            "In": timecode(p["segments"][0]["start"]),
            "Out": timecode(p["segments"][-1]["end"]) + ("" if len(eps) == 1 else f" (Ep{eps[-1]})"),
            "Sec": p["duration"], "Score": p["final_score"], "Hook": p["hook"],
            "Spoiler": "⚠" if p.get("spoiler_risk") else "",
            "Review": ", ".join(r.replace("_", " ") for r in p["review_reasons"]),
            "Status": status_of(p["promo_id"], decisions).capitalize(),
        })
    return rows


def decisions_csv(ranked, decisions):
    """The editor's decisions with timecodes and reasons: the record a team (or prompt tuning) uses."""
    out = io.StringIO()
    cols = ["decision", "reason", "note", "rank", "promo_id", "timecodes", "duration", "hook", "cliffhanger"]
    w = csv.DictWriter(out, fieldnames=cols)
    w.writeheader()
    for p in ranked:
        d = decisions.get(p["promo_id"])
        if d:
            w.writerow({"decision": d["status"], "reason": d.get("reason", ""), "note": d.get("note", ""),
                        "rank": p["rank"], "promo_id": p["promo_id"], "timecodes": timecode_text(p),
                        "duration": p["duration"], "hook": p["hook"], "cliffhanger": p["cliffhanger"]})
    return out.getvalue()


def timecode_csv(ranked):
    """Reuses report.write_timecode_csv so the app and the terminal export the exact same file."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "timecodes.csv"
        write_timecode_csv(ranked, path)
        return path.read_text(encoding="utf-8")


# ------------------------------------------------------------------ visuals
def coverage(data):
    """Each episode -> 'post' (in the post-first list), 'has' (has promos) or 'none'."""
    post = {s["episode"] for p in acquisition_list(data["ranked"]) for s in p["segments"]}
    has = {s["episode"] for p in data["ranked"] for s in p["segments"]}
    return [{"ep": n, "kind": "post" if n in post else "has" if n in has else "none"}
            for n in episode_numbers(data)]


def timeline(p, data):
    """Where each segment sits inside its episode, as left/width percentages for a bar."""
    out = []
    for s in p["segments"]:
        dur = (data.get("episodes") or {}).get(str(s["episode"])) or max(s["end"], 1.0)
        out.append({"ep": s["episode"], "left": round(100 * s["start"] / dur, 2),
                    "width": round(100 * (s["end"] - s["start"]) / dur, 2), "length": fmt(dur)})
    return out


def clip_rows(p, episodes):
    """
    The clip as a viewer sees it: script rows inside each segment, time counted from the clip's start.
    Tags: 'hook' on the row where the hook lands, 'zone' on other rows in the first 3 seconds,
    'cliff' on the last row (where the promo cuts).
    """
    rows, offset = [], 0.0
    for n, seg in enumerate(p["segments"], start=1):
        ep = episodes.get(seg["episode"])
        if ep is None:
            continue
        if len(p["segments"]) > 1:
            rows.append({"divider": f"Segment {n} · Episode {seg['episode']} · {fmt(seg['start'])} → {fmt(seg['end'])}"})
        for r in ep["lines"]:
            if seg["start"] - 0.01 <= r["start"] < seg["end"]:
                who = r["speaker"] if r["kind"] == "dialogue" else r["kind"].upper()
                rows.append({"t": round(offset + r["start"] - seg["start"], 1), "who": who,
                             "emotion": r["emotion"], "text": r["text"], "kind": r["kind"], "tag": ""})
        offset += seg["end"] - seg["start"]
    real = [r for r in rows if "t" in r]
    if real:
        hook_at = p.get("hook_offset", 0.0)
        hook_row = next((r for r in real if r["t"] >= hook_at - 0.05), real[0])
        for r in real:
            if r["t"] <= 3.0:
                r["tag"] = "zone"
        hook_row["tag"] = "hook"
        real[-1]["tag"] = "cliff"
    return rows


# ------------------------------------------------------------------ compare two runs
def _overlap_share(a, b):
    inter = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    return inter / max(min(a["end"] - a["start"], b["end"] - b["start"]), 0.01)


def compare_runs(a, b):
    """
    Two runs of the same show: which single-clip promos do both find (overlap >= 50%)?
    Only episodes BOTH runs covered are compared (a second run is often limited to the first N episodes).
    """
    singles = lambda d: [p for p in d["ranked"] if p["kind"] == "single"]
    last_ep = min(max((p["segments"][0]["episode"] for p in singles(d)), default=0) for d in (a, b))
    pa = [p for p in singles(a) if p["segments"][0]["episode"] <= last_ep]
    pb = [p for p in singles(b) if p["segments"][0]["episode"] <= last_ep]

    def matched(p, others):
        s = p["segments"][0]
        return any(o["segments"][0]["episode"] == s["episode"] and _overlap_share(s, o["segments"][0]) >= 0.5
                   for o in others)

    in_both_a = {p["promo_id"] for p in pa if matched(p, pb)}
    in_both_b = {p["promo_id"] for p in pb if matched(p, pa)}
    top = lambda ps, both: [{"id": p["promo_id"], "seg": timecode_text(p), "score": p["final_score"],
                             "both": p["promo_id"] in both} for p in sorted(ps, key=lambda x: -x["final_score"])[:5]]
    return {"episodes_compared": last_ep, "a_count": len(pa), "b_count": len(pb),
            "found_by_both": len(in_both_a), "only_a": len(pa) - len(in_both_a), "only_b": len(pb) - len(in_both_b),
            "top_a": top(pa, in_both_a), "top_b": top(pb, in_both_b)}


# ------------------------------------------------------------------ quality page
QUALITY_FILES = {
    "gold": ("_eval_gold_set.md", r"Hit rate:\*\* (\d+/\d+).*?avg end gap:\*\* ([\d.]+)s"),
    "audit": ("_audit.md", r"Promos passing all 7 checks: (\d+)"),
    "stability": ("_stability.md", r"\*\*(\d+/\d+) first-run promos"),
    "judge": ("_judge_agreement.md", r"Spearman rank correlation:\*\* (-?[\d.]+).*?red-flag agreement:\*\* (\d+/\d+)"),
}


def read_quality(source, folders=QUALITY_FOLDERS):
    """Reads the eval result files written by eval/*.py and pulls out the headline numbers."""
    out = {}
    for key, (suffix, pattern) in QUALITY_FILES.items():
        for folder in folders:
            path = Path(folder) / f"{source}{suffix}"
            if path.exists():
                text = path.read_text(encoding="utf-8")
                m = re.search(pattern, text, re.S)
                out[key] = {"text": text, "values": m.groups() if m else None}
                break
    audited = re.search(r"Promos audited: (\d+)", out.get("audit", {}).get("text", ""))
    if audited and out["audit"]["values"]:
        out["audit"]["values"] = (f"{out['audit']['values'][0]}/{audited.group(1)}",)
    return out