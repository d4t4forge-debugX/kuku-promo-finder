"""
test_app_logic.py: tests for what the app calculates (src/app_logic.py). No browser, no AI, no Kuku data.
Run:  python -m pytest -v
"""
from src import app_logic as L
from tests.test_core import fake_ep


def promo(pid, ep, start, end, score, kind="single", review=(), hook_offset=0.0):
    return {"promo_id": pid, "kind": kind, "rank": 0, "final_score": score, "duration": end - start,
            "segments": [{"episode": ep, "start": start, "end": end, "start_ts": "", "end_ts": ""}],
            "hook": "h", "cliffhanger": "c", "why": "w", "hook_type": "reveal",
            "review_reasons": list(review), "hook_offset": hook_offset, "flags": []}


def fake_run():
    ranked = [promo("E01-P1", 1, 5.0, 50.0, 9.0), promo("E02-P1", 2, 0.0, 30.0, 8.0, review=["x"]),
              promo("E40-P1", 40, 0.0, 30.0, 7.0)]
    for i, p in enumerate(ranked, 1):
        p["rank"] = i
    return {"show": "s", "episodes": {"1": 70.0, "2": 60.0, "3": 60.0, "40": 60.0}, "ranked": ranked}


def test_coverage_marks_post_first_has_and_none():
    kinds = {c["ep"]: c["kind"] for c in L.coverage(fake_run())}
    assert kinds == {1: "post", 2: "has", 3: "none", 40: "has"}   # Ep 2 has a review flag -> not post-first


def test_filters_and_decisions():
    run, dec = fake_run(), {"E40-P1": {"status": "rejected", "reason": "Spoiler"}}
    assert [p["promo_id"] for p in L.filter_promos(run["ranked"], "Post first", dec)] == ["E01-P1"]
    assert [p["promo_id"] for p in L.filter_promos(run["ranked"], "Needs review", dec)] == ["E02-P1"]
    assert [p["promo_id"] for p in L.filter_promos(run["ranked"], "Rejected", dec)] == ["E40-P1"]
    csv_text = L.decisions_csv(run["ranked"], dec)
    assert "rejected,Spoiler" in csv_text and "E01-P1" not in csv_text


def test_table_has_timecodes():
    row = L.table_rows(fake_run()["ranked"], {})[0]
    assert row["In"] == "00:00:05:00" and row["Out"] == "00:00:50:00" and row["Ep"] == "1"


def test_timeline_percentages():
    seg = L.timeline(fake_run()["ranked"][0], fake_run())[0]
    assert round(seg["left"], 1) == round(100 * 5 / 70, 1) and round(seg["width"], 1) == round(100 * 45 / 70, 1)


def test_clip_rows_tag_hook_and_cliffhanger():
    p = promo("P", 1, 5.0, 50.0, 9.0)                 # fake episode rows start at 5.0, 8.5, 12, 20, 30
    rows = L.clip_rows(p, {1: fake_ep()})
    tags = [r["tag"] for r in rows]
    assert rows[0]["t"] == 0.0 and tags[0] == "hook"   # hook lands on the first row
    assert tags[-1] == "cliff"                        # cut point = last row
    assert "zone" not in tags[1:] or rows[tags.index("zone")]["t"] <= 3.0


def test_compare_identical_runs_all_match():
    run = fake_run()
    r = L.compare_runs(run, run)
    assert r["found_by_both"] == r["a_count"] and r["only_a"] == 0 and r["only_b"] == 0


def test_read_quality_parses_eval_files(tmp_path):
    (tmp_path / "s_eval_gold_set.md").write_text("**Hit rate:** 4/5 gold picks | **avg start gap:** 13.2s | **avg end gap:** 1.4s")
    (tmp_path / "s_audit.md").write_text("- Promos audited: 79\n- Promos passing all 7 checks: 79")
    q = L.read_quality("s", folders=[tmp_path])
    assert q["gold"]["values"] == ("4/5", "1.4") and q["audit"]["values"] == ("79/79",)
    assert "stability" not in q