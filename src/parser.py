"""
parser.py: turns raw screenplay .txt files into clean, timestamped data.

NO AI in this file. Parsing is exact and free, so we do it with plain code.
Every line of the script becomes one dict:
    {"id": "L012", "start": 11.3, "end": 13.1, "kind": "dialogue",
     "speaker": "MATRIARCH", "emotion": "Cold, Commanding", "text": "...", ...}

Run:  python -m src.parser data/raw/broken_soldier
"""
import json
import re
import sys
import zipfile
from pathlib import Path

# ---------- patterns (regular expressions) ----------
TIME_RE = re.compile(r"^Start: \((\d{2}):(\d{2}\.\d{2})\) \| End: \((\d{2}):(\d{2}\.\d{2})\)$")
HEADER_RE = re.compile(r"^\*\*(.+?):\*\*$")            # **CAMERA:**  or  **LADY JULIANA (Confused):**
SPEAKER_RE = re.compile(r"^(.+?)\s*\((.*)\)$")         # LADY JULIANA (Confused, Breathless)
SCENE_RE = re.compile(r"^SCENE\s+(\d+)")
SCENE_TIME_RE = re.compile(r"^Scene (start|end): (\d{2}):(\d{2}\.\d{2})$")

NON_DIALOGUE = {"CAMERA": "camera", "ACTION": "action", "SOUND FX": "sfx"}


def to_seconds(mm, ss):
    """'01', '58.88' -> 118.88"""
    return int(mm) * 60 + float(ss)


def fmt(seconds):
    """118.88 -> '01:58.88' (same style as the scripts)"""
    m = int(seconds // 60)
    return f"{m:02d}:{seconds - m * 60:05.2f}"


def classify(header):
    """Header text -> (kind, speaker, emotion)."""
    if header in NON_DIALOGUE:
        return NON_DIALOGUE[header], None, ""
    m = SPEAKER_RE.match(header)
    if m:
        return "dialogue", m.group(1).strip(), m.group(2).strip()
    return "dialogue", header, ""


def parse_episode(text, source_name=""):
    """Parse ONE episode's text into a dict with metadata + a list of timed lines."""
    ep = {"episode": None, "logline": "", "continuity": "", "source": source_name,
          "scenes": [], "lines": []}
    rows = text.splitlines()
    header = None          # the **HEADER:** we saw most recently, waiting for its Start/End line
    scene_no = 0
    i = 0
    while i < len(rows):
        raw = rows[i].strip()

        if raw.startswith("EPISODE NUMBER:"):
            num = re.search(r"\d+", raw)
            ep["episode"] = int(num.group()) if num else None
        elif raw.startswith("EPISODE LOGLINE:"):
            ep["logline"] = raw.split(":", 1)[1].strip()
        elif raw.startswith("CONTINUITY NOTES:"):
            ep["continuity"] = raw.split(":", 1)[1].strip()
        elif SCENE_RE.match(raw):
            scene_no = int(SCENE_RE.match(raw).group(1))
            ep["scenes"].append({"scene": scene_no, "heading": "", "start": None, "end": None})
        elif raw.startswith("Scene heading:") and ep["scenes"]:
            ep["scenes"][-1]["heading"] = raw.split(":", 1)[1].strip()
        elif SCENE_TIME_RE.match(raw) and ep["scenes"]:
            m = SCENE_TIME_RE.match(raw)
            ep["scenes"][-1][m.group(1)] = to_seconds(m.group(2), m.group(3))
        elif HEADER_RE.match(raw):
            header = HEADER_RE.match(raw).group(1).strip()
        elif header and TIME_RE.match(raw):
            t = TIME_RE.match(raw)
            # the text is every non-empty row after the Start/End row, until a blank row
            j, parts = i + 1, []
            while j < len(rows) and rows[j].strip():
                parts.append(rows[j].strip())
                j += 1
            kind, speaker, emotion = classify(header)
            ep["lines"].append({
                "start": to_seconds(t.group(1), t.group(2)),
                "end": to_seconds(t.group(3), t.group(4)),
                "kind": kind, "speaker": speaker, "emotion": emotion,
                "text": " ".join(parts), "scene": scene_no,
            })
            header = None
            i = j
            continue
        i += 1

    # sort by time (stable: ties keep file order), then give each line a short ID
    ep["lines"].sort(key=lambda r: r["start"])
    for n, line in enumerate(ep["lines"], start=1):
        line["id"] = f"L{n:03d}"
        line["episode"] = ep["episode"]
    ep["duration"] = max((r["end"] for r in ep["lines"]), default=0.0)
    return ep


def load_show(path):
    """Load every episode from a folder of .txt files OR a .zip. Returns episodes sorted by number."""
    path = Path(path)
    texts = []
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.endswith(".txt") and not name.startswith("__MACOSX"):
                    texts.append((Path(name).name, z.read(name).decode("utf-8", errors="replace")))
    else:
        for f in sorted(path.glob("*.txt")):
            texts.append((f.name, f.read_text(encoding="utf-8", errors="replace")))
    if not texts:
        raise FileNotFoundError(f"No .txt scripts found in {path}")

    episodes = [parse_episode(txt, name) for name, txt in texts]
    missing = [e["source"] for e in episodes if e["episode"] is None]
    if missing:
        print(f"WARNING: no episode number found in {missing}")
    return sorted(episodes, key=lambda e: e["episode"] or 0)


def sanity_check(episodes):
    """Catch broken data early instead of getting weird promos later."""
    problems = []
    for ep in episodes:
        if not ep["lines"]:
            problems.append(f"Ep {ep['episode']}: no lines parsed")
        for r in ep["lines"]:
            if r["end"] < r["start"]:
                problems.append(f"Ep {ep['episode']} {r['id']}: end before start")
    return problems


def render_for_llm(ep):
    """
    Turn one episode into compact text for the AI. Each row starts with a line ID.
    The AI answers with IDs (e.g. L012), and OUR code looks up the exact timestamps,
    so the AI can never invent a timestamp.
    """
    out = [f"EPISODE {ep['episode']}: {ep['logline']}"]
    for r in ep["lines"]:
        span = f"[{fmt(r['start'])}-{fmt(r['end'])}]"
        if r["kind"] == "dialogue":
            emo = f" ({r['emotion']})" if r["emotion"] else ""
            out.append(f'{r["id"]} {span} {r["speaker"]}{emo}: {r["text"]}')
        else:
            out.append(f'{r["id"]} {span} {r["kind"].upper()}: {r["text"]}')
    return "\n".join(out)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "data/raw/broken_soldier"
    episodes = load_show(src)

    total = sum(e["duration"] for e in episodes)
    kinds = {}
    for e in episodes:
        for r in e["lines"]:
            kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1

    print(f"Loaded {len(episodes)} episodes from {src}")
    print(f"Total runtime: {total / 60:.1f} min | avg episode {total / len(episodes):.0f}s")
    print(f"Lines by kind: {kinds}")
    problems = sanity_check(episodes)
    print(f"Sanity problems: {len(problems)}")
    for p in problems[:10]:
        print("  -", p)

    print("\nFirst 12 rows of Episode", episodes[0]["episode"], "as the AI will see them:")
    print("\n".join(render_for_llm(episodes[0]).splitlines()[:12]))

    out = Path("outputs/parsed") / f"{Path(src).stem}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(episodes, indent=2, ensure_ascii=False))
    print(f"\nSaved -> {out}")