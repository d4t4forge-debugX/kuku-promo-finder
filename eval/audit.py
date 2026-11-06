"""
audit.py: an INDEPENDENT second check of the final promos.

It does NOT import anything from src/ (on purpose). It re-reads the RAW script files with its own
tiny reader, then checks every promo in outputs/final/<show>_ranked.json against them.
Like a second accountant re-checking the books without trusting the first one's spreadsheet.

Checks per promo:
  1. every segment's episode exists
  2. every cut point is a real line boundary in the raw script
  3. total length is 20-60 seconds
  4. the hook lands within 3 seconds of the start
  5. no cut falls in the middle of a spoken line
  6. the printed timestamps (mm:ss.cc) match the numbers
  7. the promo was actually judged (has judge scores)
Plus: the CSV has exactly one row per ranked promo.

Run:  python -m eval.audit data/raw/broken_soldier
"""
import csv
import json
import re
import sys
import zipfile
from pathlib import Path

TIME = re.compile(r"Start: \((\d{1,2}):(\d{2}\.\d{2})\) \| End: \((\d{1,2}):(\d{2}\.\d{2})\)")
HEAD = re.compile(r"^\*\*(.+?):\*\*$")
EP_NO = re.compile(r"EPISODE NUMBER:\D*(\d+)", re.I)   # "Episode 1", "Ep.2 (Part B)"
NON_DIALOGUE = {"CAMERA", "ACTION", "SOUND FX"}
TOL = 0.011   # timestamps have 2 decimals; allow rounding noise


def read_raw(src):
    """Raw scripts -> {episode: [(start, end, is_dialogue), ...]} using our OWN reader."""
    src = Path(src)
    texts = []
    if src.suffix == ".zip":
        with zipfile.ZipFile(src) as z:
            texts = [(Path(n).name, z.read(n).decode("utf-8", "replace")) for n in z.namelist()
                     if n.endswith(".txt") and not n.startswith("__MACOSX")]
    else:
        texts = [(f.name, f.read_text(encoding="utf-8", errors="replace")) for f in src.glob("*.txt")]
    episodes = {}
    for name, text in texts:
        m = EP_NO.search(text) or re.search(r"(\d+)", Path(name).stem)   # header, else file name
        if not m:
            raise SystemExit(f"AUDIT STOPPED: no episode number in {name}")
        num = int(m.group(1))
        rows, header = [], None
        for line in text.splitlines():
            line = line.strip()
            h = HEAD.match(line)
            if h:
                header = h.group(1).strip()
                continue
            t = TIME.match(line)
            if t and header:
                start = int(t.group(1)) * 60 + float(t.group(2))
                end = int(t.group(3)) * 60 + float(t.group(4))
                rows.append((start, end, header not in NON_DIALOGUE))
                header = None
        episodes[num] = rows
    return episodes


def ts(seconds):
    m = int(seconds // 60)
    return f"{m:02d}:{seconds - m * 60:05.2f}"


def audit_promo(p, raw):
    problems = []
    segs = p["segments"]
    for s in segs:
        rows = raw.get(s["episode"])
        if rows is None:
            problems.append(f"episode {s['episode']} not in raw scripts")
            continue
        starts = [r[0] for r in rows]
        ends = [r[1] for r in rows]
        if not any(abs(s["start"] - x) < TOL for x in starts):
            problems.append(f"Ep{s['episode']} start {s['start']} is not a line start")
        if not any(abs(s["end"] - x) < TOL for x in ends):
            problems.append(f"Ep{s['episode']} end {s['end']} is not a line end")
        for (a, b, spoken) in rows:
            if spoken and (a + TOL < s["start"] < b - TOL or a + TOL < s["end"] < b - TOL):
                problems.append(f"Ep{s['episode']} cut inside dialogue {ts(a)}-{ts(b)}")
                break
        if s.get("start_ts") != ts(s["start"]) or s.get("end_ts") != ts(s["end"]):
            problems.append(f"Ep{s['episode']} printed timestamps don't match numbers")
    length = sum(s["end"] - s["start"] for s in segs)
    if not (20 - TOL <= length <= 60 + TOL):
        problems.append(f"length {length:.2f}s outside 20-60s")
    hook_offset = p["hook_time"] - segs[0]["start"]
    if hook_offset > 3 + TOL or hook_offset < -TOL:
        problems.append(f"hook at +{hook_offset:.2f}s (must be 0-3s)")
    if not p.get("judge") or p["judge"].get("overall") is None:
        problems.append("not judged")
    return problems


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "data/raw/broken_soldier"
    show = Path(src).stem
    raw = read_raw(src)
    ranked = json.loads((Path("outputs/final") / f"{show}_ranked.json").read_text())["ranked"]

    failures = {p["promo_id"]: audit_promo(p, raw) for p in ranked}
    failures = {k: v for k, v in failures.items() if v}

    csv_path = Path("outputs/final") / f"{show}_promos.csv"
    csv_rows = sum(1 for _ in csv.DictReader(open(csv_path, encoding="utf-8"))) if csv_path.exists() else -1

    lines = [f"# Independent audit: {show}", "",
             f"- Raw episodes read independently: {len(raw)}",
             f"- Promos audited: {len(ranked)}",
             f"- Promos passing all 7 checks: {len(ranked) - len(failures)}",
             f"- CSV rows: {csv_rows} ({'matches' if csv_rows == len(ranked) else 'MISMATCH'})", ""]
    if failures:
        lines.append("## Failures")
        lines += [f"- **{pid}**: " + "; ".join(probs) for pid, probs in failures.items()]
    else:
        lines.append("All promos passed every check.")
    out = Path("outputs/final") / f"{show}_audit.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nSaved -> {out}")