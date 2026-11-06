"""
run.py: the WHOLE pipeline in one command. This is what you run live in the interview.

    python run.py data/raw/broken_soldier          # a folder of scripts
    python run.py path/to/new_show.zip             # or a zip
    LLM_MODEL=some-other-model python run.py ...   # swap the model without touching code
    RUN_TAG=gptoss LLM_PROVIDER=groq LLM_MODEL=openai/gpt-oss-120b python run.py ... --limit 10
                                                   # a second run of the same show, kept separately

Every AI step is cached, so a re-run only pays for what is missing.
"""
import argparse
import time

from src.llm_client import current_model
from src.pipeline import run_pipeline
from src.ranker import judge_model
from src.report import seg_text

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Find, check and rank promos for a microdrama show")
    ap.add_argument("src", help="folder of episode .txt scripts, or a .zip of them")
    ap.add_argument("--workers", type=int, default=4, help="parallel AI calls (lower if you hit 429 rate limits)")
    ap.add_argument("--force", action="store_true", help="ignore all caches and call the AI again")
    ap.add_argument("--no-stitch", action="store_true", help="skip cross-episode montage promos")
    ap.add_argument("--limit", type=int, help="only the first N episodes (quick test runs)")
    args = ap.parse_args()

    t0 = time.time()
    print(f"=== Promo finder | picker: {current_model()} | judge: {judge_model()} ===\n")
    try:
        out = run_pipeline(args.src, workers=args.workers, force=args.force,
                           stitch=not args.no_stitch, limit=args.limit)
    except RuntimeError as e:          # a clear one-line reason instead of a long traceback
        raise SystemExit(f"\nSTOPPED: {e}")

    print("\nPOST FIRST (acquisition list):")
    for i, p in enumerate(out["acquisition"], 1):
        print(f"  {i}. {p['promo_id']:<7} {seg_text(p)} ({p['duration']}s, score {p['final_score']})")
        print(f"     hook: {p['hook'][:100]}")
    if not out["acquisition"]:
        print("  (none: every early-episode promo has a review flag; see 'Needs a human look' in the report)")
    print(f"\nDone in {time.time() - t0:.0f}s | tokens this run: {out['usage']}")
    print(f"Report    -> {out['report']}\nCSV       -> {out['csv']}\nTimecodes -> {out['timecodes']}")