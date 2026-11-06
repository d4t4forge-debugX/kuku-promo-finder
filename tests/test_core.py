"""
test_core.py: automated tests for the parts that must ALWAYS be right. No AI, no API key, no cost.

Uses a tiny MADE-UP episode (not Kuku's confidential scripts), so these tests can run anywhere,
including on GitHub.

Run:  python -m pytest -v
"""
import json

from eval.evaluate import overlap, secs
from src.beats import attach_times, parse_json
from src.parser import fmt, parse_episode, render_for_llm, show_key, timecode, to_seconds
from src.validators import dedupe, validate

# A fake 70-second episode in the same format as the real scripts.
FAKE_SCRIPT = """EPISODE NUMBER: Episode 1
EPISODE LOGLINE: A test bride is betrayed.
CONTINUITY NOTES: none

--- SCRIPT START ---

SCENE 01
Scene heading: INT. CHAPEL - DAY
Scene start: 00:00.00
Scene end: 01:10.00

Actions and dialogue:

**CAMERA:**
Start: (00:00.00) | End: (00:05.00)
Wide shot of the chapel.

**VILLAIN (Cold):**
Start: (00:05.00) | End: (00:08.00)
"The deal is done."

**BRIDE (Shocked):**
Start: (00:08.50) | End: (00:12.00)
"No..."

**ACTION:**
Start: (00:12.00) | End: (00:20.00)
The bride falls to her knees.

**VILLAIN (Mocking):**
Start: (00:20.00) | End: (00:30.00)
""You will never leave.""

**CAMERA:**
Start: (00:30.00) | End: (00:50.00)
Slow push in on the doors.

**STRANGER (Grave):**
Start: (00:50.00) | End: (01:05.00)
"Marry me."

**SOUND FX:**
Start: (01:05.00) | End: (01:10.00)
Ominous drone.

--- SCRIPT END ---
"""


def fake_ep():
    return parse_episode(FAKE_SCRIPT, "fake.txt")


def fake_promo(start, end, hook, pid="P"):
    return {"promo_id": pid, "segments": [{"episode": 1, "start": start, "end": end}],
            "hook_time": hook, "ai_score": 20}


# ---------------- parser ----------------
def test_time_conversion_roundtrip():
    assert to_seconds("01", "58.88") == 118.88
    assert fmt(118.88) == "01:58.88"
    assert fmt(0) == "00:00.00"


def test_parse_episode_reads_everything():
    ep = fake_ep()
    assert ep["episode"] == 1
    assert ep["logline"] == "A test bride is betrayed."
    assert len(ep["lines"]) == 8
    kinds = [r["kind"] for r in ep["lines"]]
    assert kinds.count("dialogue") == 4 and kinds.count("camera") == 2 and kinds.count("sfx") == 1
    villain = ep["lines"][1]
    assert villain["speaker"] == "VILLAIN" and villain["emotion"] == "Cold"
    assert villain["text"] == '"The deal is done."'
    assert ep["lines"][0]["id"] == "L001"
    assert ep["duration"] == 70.0


def test_render_for_llm_has_ids_and_times():
    text = render_for_llm(fake_ep())
    assert "L002 [00:05.00-00:08.00] VILLAIN (Cold)" in text


# ---------------- AI answer handling ----------------
def test_parse_json_handles_code_fences_and_chatter():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure! Here it is: {"a": 2} hope it helps') == {"a": 2}


def test_hallucinated_or_backwards_ids_are_dropped():
    ep = fake_ep()
    ai = {"promos": [
        {"start_id": "L002", "hook_id": "L002", "end_id": "L007"},   # valid
        {"start_id": "L999", "end_id": "L007"},                       # made-up ID
        {"start_id": "L007", "end_id": "L002"},                       # backwards
    ], "moments": [{"line_id": "L005"}, {"line_id": "LXYZ"}]}
    promos, moments, report = attach_times(json.loads(json.dumps(ai)), ep)
    assert len(promos) == 1 and promos[0]["start"] == 5.0 and promos[0]["end"] == 65.0
    assert report["bad_ids"] == 2 and report["bad_order"] == 1
    assert len(moments) == 1


# ---------------- validators (the brief's hard rules) ----------------
def test_good_promo_passes():
    p = validate(fake_promo(5.0, 30.0, 5.0), {1: fake_ep()})
    assert p["status"] == "ok" and p["duration"] == 25.0 and p["hook_offset"] == 0.0


def test_too_short_is_rejected():
    p = validate(fake_promo(5.0, 12.0, 5.0), {1: fake_ep()})
    assert p["status"] == "rejected" and "too_short" in p["flags"]


def test_cut_inside_dialogue_is_moved_out():
    p = validate(fake_promo(5.0, 25.0, 5.0), {1: fake_ep()})   # 25.0 is inside "Nobody will ever save you" (20-30)
    assert p["segments"][0]["end"] == 30.0


def test_start_inside_dialogue_moves_to_clean_boundary():
    p = validate(fake_promo(6.0, 40.0, 6.0), {1: fake_ep()})   # 6.0 is inside the villain's line (5-8)
    assert p["segments"][0]["start"] == 5.0


def test_late_hook_moves_start_to_a_clean_row_start():
    p = validate(fake_promo(0.0, 50.0, 20.0), {1: fake_ep()})  # hook at 20s, 20s too late
    assert "moved_start_to_hook" in p["flags"]
    assert p["segments"][0]["start"] in {r["start"] for r in fake_ep()["lines"]}
    assert 0 <= p["hook_offset"] <= 3


def test_too_long_is_trimmed_to_60s():
    p = validate(fake_promo(0.0, 70.0, 0.0), {1: fake_ep()})
    assert p["duration"] <= 60.0 and any(f.startswith("trimmed_end") for f in p["flags"])


def test_duplicates_keep_the_better_one():
    ep = {1: fake_ep()}
    a = validate(fake_promo(5.0, 50.0, 5.0, "A"), ep)
    b = validate(fake_promo(5.0, 30.0, 5.0, "B"), ep)
    b["ai_score"] = 10
    dedupe([a, b])
    assert a["status"] == "ok" and b["status"] == "rejected"


def test_timecode_for_editors():
    assert timecode(0) == "00:00:00:00"
    assert timecode(5.5) == "00:00:05:15"          # 0.5s = 15 frames at 30 fps
    assert timecode(84.0) == "00:01:24:00"
    assert timecode(3661.0) == "01:01:01:00"


def test_show_key_uses_run_tag(monkeypatch):
    monkeypatch.delenv("RUN_TAG", raising=False)
    assert show_key("data/raw/broken_soldier") == "broken_soldier"
    monkeypatch.setenv("RUN_TAG", "gptoss")
    assert show_key("data/raw/broken_soldier") == "broken_soldier__gptoss"


# ---------------- evaluation maths ----------------
def test_eval_helpers():
    assert secs("01:24.00") == 84.0
    assert overlap(0, 10, 5, 20) == 5
    assert overlap(0, 10, 20, 30) == 0


if __name__ == "__main__":   # lets you run without pytest:  python -m tests.test_core
    tests = [f for name, f in dict(globals()).items() if name.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"\nAll {len(tests)} tests passed.")