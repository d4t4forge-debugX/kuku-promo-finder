"""
beats.py: STEP 3. The first AI step.

For each episode: send the line-ID'd script to the AI, get back promo candidates
and key moments as JSON, then convert line IDs -> exact timestamps with OUR code.

Results are CACHED per episode in outputs/beats/<show>/ep_XXX.json:
re-running skips finished episodes (free + resumable). Use --force to redo.

Run:  python -m src.beats data/raw/broken_soldier --limit 3
"""
import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.llm_client import USAGE, chat, current_model
from src.parser import fmt, load_show, render_for_llm, show_key
from src.prompts import PROMPT_VERSION, SYSTEM_EDITOR, beats_prompt


def parse_json(text):
    """AI replies sometimes wrap JSON in ```json fences or add chatter. Dig the JSON out."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)   # first '{' to last '}'
        if m:
            return json.loads(m.group())
        raise


def attach_times(result, ep):
    """
    The AI gave us line IDs. Look up real timestamps and DROP anything that
    points at an ID that doesn't exist (a hallucination) or is in the wrong order.
    """
    by_id = {r["id"]: r for r in ep["lines"]}
    report = {"promos_in": 0, "promos_kept": 0, "bad_ids": 0, "bad_order": 0,
              "moments_in": 0, "moments_kept": 0}

    promos = []
    for p in result.get("promos", []) or []:
        report["promos_in"] += 1
        p["hook_id"] = p.get("hook_id") or p.get("start_id")
        ids = [p.get("start_id"), p["hook_id"], p.get("end_id")]
        if not all(i in by_id for i in ids):
            report["bad_ids"] += 1
            continue
        s, h, e = by_id[ids[0]], by_id[ids[1]], by_id[ids[2]]
        if e["end"] <= s["start"] or h["start"] < s["start"]:
            report["bad_order"] += 1
            continue
        p.update({
            "episode": ep["episode"],
            "start": s["start"], "end": e["end"],
            "hook_time": h["start"],
            "duration": round(e["end"] - s["start"], 2),
            "start_ts": fmt(s["start"]), "end_ts": fmt(e["end"]),
        })
        promos.append(p)
    report["promos_kept"] = len(promos)

    moments = []
    for m in result.get("moments", []) or []:
        report["moments_in"] += 1
        r = by_id.get(m.get("line_id"))
        if not r:
            report["bad_ids"] += 1
            continue
        m.update({"episode": ep["episode"], "start": r["start"], "end": r["end"],
                  "text": r["text"], "speaker": r["speaker"]})
        moments.append(m)
    report["moments_kept"] = len(moments)
    return promos, moments, report


def extract_episode(ep, premise, cache_dir, force=False):
    """One episode -> one AI call -> cached JSON file. Returns the saved record."""
    path = cache_dir / f"ep_{ep['episode']:03d}.json"
    if path.exists() and not force:
        return json.loads(path.read_text()), True

    t0 = time.time()
    raw = chat(beats_prompt(premise, render_for_llm(ep)), system=SYSTEM_EDITOR,
               json_mode=True, temperature=0.2)
    try:
        parsed = parse_json(raw)
        error = None
    except Exception as e:   # keep going; record the failure honestly
        parsed, error = {}, f"{type(e).__name__}: {e}"
    promos, moments, report = attach_times(parsed, ep)

    record = {
        "episode": ep["episode"], "model": current_model(), "prompt_version": PROMPT_VERSION,
        "seconds": round(time.time() - t0, 1), "parse_error": error, "report": report,
        "promos": promos, "moments": moments,
        "raw_response": raw,          # unedited AI output, kept for the 'raw outputs' deliverable
    }
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return record, False


def run_show(src, workers=4, force=False, limit=None):
    episodes = load_show(src)
    if limit:
        episodes = episodes[:limit]
    premise = episodes[0]["logline"]
    cache_dir = Path("outputs/beats") / show_key(src)
    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"Model: {current_model()} | prompt {PROMPT_VERSION} | {len(episodes)} episodes | {workers} workers")
    t0 = time.time()
    records = []
    # ThreadPoolExecutor = several AI calls in flight at once (the waiting is network time, not CPU)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(extract_episode, ep, premise, cache_dir, force): ep["episode"] for ep in episodes}
        for fut in as_completed(futures):
            n = futures[fut]
            try:
                rec, cached = fut.result()
                r = rec["report"]
                tag = "cached" if cached else f"{rec['seconds']}s"
                flag = f"  PARSE ERROR: {rec['parse_error']}" if rec["parse_error"] else ""
                print(f"  Ep {n:>3}: {r['promos_kept']}/{r['promos_in']} promos, "
                      f"{r['moments_kept']} moments, bad_ids={r['bad_ids']} bad_order={r['bad_order']} [{tag}]{flag}")
                records.append(rec)
            except Exception as e:
                print(f"  Ep {n:>3}: FAILED -> {type(e).__name__}: {e}")

    records.sort(key=lambda r: r["episode"])
    tot = lambda k: sum(r["report"][k] for r in records)
    print(f"\nDone in {time.time() - t0:.0f}s | episodes ok: {len(records)}/{len(episodes)}")
    print(f"Promos kept {tot('promos_kept')}/{tot('promos_in')} | moments {tot('moments_kept')} | "
          f"bad_ids {tot('bad_ids')} | bad_order {tot('bad_order')}")
    print(f"Tokens this run (excludes cached): {USAGE}")
    return records


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Step 3: AI finds promo candidates + key moments per episode")
    ap.add_argument("src", help="folder of .txt scripts or a .zip")
    ap.add_argument("--limit", type=int, help="only the first N episodes (for testing)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--force", action="store_true", help="ignore cache and call the AI again")
    args = ap.parse_args()
    run_show(args.src, workers=args.workers, force=args.force, limit=args.limit)