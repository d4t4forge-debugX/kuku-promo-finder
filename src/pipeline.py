"""
pipeline.py: the WHOLE pipeline as one function.

Both run.py (terminal) and app.py (web) call run_pipeline(), so they always run exactly
the same steps in the same order. One source of truth = no copies that drift apart.
"""
from pathlib import Path

from src.assembler import build_single_promos
from src.beats import run_show
from src.llm_client import USAGE
from src.parser import show_key
from src.ranker import rank_show
from src.report import write_report
from src.stitcher import build_stitched


def run_pipeline(src, workers=4, force=False, stitch=True, limit=None, step=print):
    """
    parse -> AI beats -> rule checks -> AI montages -> AI judge -> report.
    `step` is called with a short message before each stage (print in the terminal, a status line in the app).
    Returns where everything was saved plus the post-first list.
    """
    step("[1/5] AI reads every episode (beats)...")
    run_show(src, workers=workers, force=force, limit=limit)

    step("[2/5] Rule checks on single-clip promos...")
    promos, _ = build_single_promos(src)
    step(f"      {sum(p['status'] != 'rejected' for p in promos)} usable of {len(promos)}")

    if stitch:
        step("[3/5] AI builds cross-episode montages...")
        result, _ = build_stitched(src, force=force)
        step(f"      {len(result['promos'])} montages ({result['bad_ids']} invalid dropped)")
    else:
        step("[3/5] Montages skipped")

    step("[4/5] Independent AI judge scores every promo...")
    rank_show(src, workers=workers, force=force)

    step("[5/5] Writing report...")
    acq, md_path, csv_path = write_report(src)

    final = Path("outputs/final")
    show = show_key(src)
    return {"show": show, "acquisition": acq,
            "ranked": final / f"{show}_ranked.json", "report": md_path, "csv": csv_path,
            "timecodes": final / f"{show}_timecodes.csv", "usage": dict(USAGE)}