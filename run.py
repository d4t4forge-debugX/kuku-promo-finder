"""
run.py: the WHOLE pipeline in one command. This is what you run live in the interview.

    python run.py data/raw/broken_soldier          # a folder of scripts
    python run.py path/to/new_show.zip             # or a zip
    LLM_MODEL=some-other-model python run.py ...   # swap the model without touching code

Steps: parse -> AI beats per episode -> rule checks -> AI montages -> AI judge -> report.
Every AI step is cached, so a re-run only pays for what is missing.
"""
import argparse
import time

from src.assembler import build_single_promos
from src.beats import run_show
from src.llm_client import USAGE, current_model
from src.ranker import judge_model, rank_show
from src.report import seg_text, write_report
from src.stitcher import build_stitched

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Find, check and rank promos for a microdrama show")
    ap.add_argument("src", help="folder of episode .txt scripts, or a .zip of them")
    ap.add_argument("--workers", type=int, default=4, help="parallel AI calls (lower if you hit 429 rate limits)")
    ap.add_argument("--force", action="store_true", help="ignore all caches and call the AI again")
    ap.add_argument("--no-stitch", action="store_true", help="skip cross-episode montage promos")
    args = ap.parse_args()

    t0 = time.time()
    print(f"=== Promo finder | picker: {current_model()} | judge: {judge_model()} ===\n")

    print("[1/5] AI reads every episode (beats)...")
    run_show(args.src, workers=args.workers, force=args.force)

    print("\n[2/5] Rule checks on single-clip promos...")
    promos, _ = build_single_promos(args.src)
    print(f"  {sum(p['status'] != 'rejected' for p in promos)} usable of {len(promos)}")

    if not args.no_stitch:
        print("\n[3/5] AI builds cross-episode montages...")
        result, _ = build_stitched(args.src, force=args.force)
        print(f"  {len(result['promos'])} montages ({result['bad_ids']} invalid dropped)")
    else:
        print("\n[3/5] Montages skipped")

    print("\n[4/5] Independent AI judge scores every promo...")
    ranked, _, _ = rank_show(args.src, workers=args.workers, force=args.force)

    print("\n[5/5] Writing report...")
    acq, md_path, csv_path = write_report(args.src)

    print("\nPOST FIRST (acquisition list):")
    for i, p in enumerate(acq, 1):
        print(f"  {i}. {p['promo_id']:<7} {seg_text(p)} ({p['duration']}s, score {p['final_score']})")
        print(f"     hook: {p['hook'][:100]}")
    print(f"\nDone in {time.time() - t0:.0f}s | tokens this run: {USAGE}")
    print(f"Report -> {md_path}\nCSV    -> {csv_path}")