"""
validators.py: hard rules, enforced by CODE (never trusted to the AI).

The brief's rules become checks:
  - 20-60 seconds long
  - the hook lands in the first 3 seconds
  - never cut a line of dialogue in half
Each promo comes out with: status ok / fixed / rejected, plus a list of flags explaining why.
"""
MIN_LEN, MAX_LEN, HOOK_WINDOW = 20.0, 60.0, 3.0


def seg_len(seg):
    return seg["end"] - seg["start"]


def total_len(promo):
    return round(sum(seg_len(s) for s in promo["segments"]), 2)


def clean_starts(ep):
    """Row start times where a clip may begin: a real row boundary that is not inside someone's spoken line."""
    spoken = [(r["start"], r["end"]) for r in ep["lines"] if r["kind"] == "dialogue"]
    return sorted({r["start"] for r in ep["lines"]
                   if not any(a + 0.011 < r["start"] < b - 0.011 for a, b in spoken)})


def snap(seg, ep):
    """
    Move cut points to clean places:
      - the END never falls inside a spoken line (move it out to the line's end)
      - the START is a clean row start (real boundary, not mid-dialogue); if not, move back to the previous one
    """
    start, end = seg["start"], seg["end"]
    for r in ep["lines"]:
        if r["kind"] == "dialogue" and r["start"] < end < r["end"]:
            end = r["end"]
    ok = clean_starts(ep)
    if not any(abs(start - x) < 0.011 for x in ok):
        earlier = [x for x in ok if x <= start]
        start = max(earlier) if earlier else start
    return start, end


def last_clean_end_before(ep, start, limit):
    """Latest dialogue/sfx line end that is <= limit (a clean place to cut early)."""
    ends = [r["end"] for r in ep["lines"]
            if r["kind"] in ("dialogue", "sfx") and start < r["end"] <= limit]
    return max(ends) if ends else None


def dialogue_share(seg, ep):
    """How much of the segment has someone speaking (0..1). Low = mostly visual."""
    spoken = 0.0
    for r in ep["lines"]:
        if r["kind"] == "dialogue":
            overlap = min(r["end"], seg["end"]) - max(r["start"], seg["start"])
            spoken += max(0.0, overlap)
    return spoken / max(seg_len(seg), 0.01)


def validate(promo, episodes_by_num):
    """Check + auto-fix one promo in place. Returns the promo with 'status' and 'flags'."""
    flags = []
    status = "ok"

    # 1) clean cuts on every segment
    for seg in promo["segments"]:
        ep = episodes_by_num[seg["episode"]]
        new_start, new_end = snap(seg, ep)
        if (new_start, new_end) != (seg["start"], seg["end"]):
            seg["start"], seg["end"] = new_start, new_end
            flags.append("snapped_to_line_boundary")
            status = "fixed"

    # 2) hook must land in the first 3 seconds
    first = promo["segments"][0]
    hook_offset = promo["hook_time"] - first["start"]
    if hook_offset > HOOK_WINDOW:
        # earliest real row start within the 3s before the hook (a clean cut with a tiny lead-in)
        ep = episodes_by_num[first["episode"]]
        window = [x for x in clean_starts(ep)
                  if promo["hook_time"] - HOOK_WINDOW <= x <= promo["hook_time"]]
        first["start"] = min(window) if window else promo["hook_time"]
        flags.append("moved_start_to_hook")
        status = "fixed"
    promo["hook_offset"] = round(promo["hook_time"] - first["start"], 2)

    # 3) length 20-60s
    length = total_len(promo)
    if length > MAX_LEN:
        last = promo["segments"][-1]
        ep = episodes_by_num[last["episode"]]
        overflow = length - MAX_LEN
        cut = last_clean_end_before(ep, last["start"], last["end"] - overflow)
        if cut:
            last["end"] = cut
            flags.append("trimmed_end_to_60s_cliffhanger_may_be_lost")
            status = "fixed"
        else:
            flags.append("too_long")
            status = "rejected"
    if total_len(promo) < MIN_LEN:
        flags.append("too_short")
        status = "rejected"

    # 4) helpful signals for ranking / quality report
    last = promo["segments"][-1]
    last_ep = episodes_by_num[last["episode"]]
    if last["end"] >= last_ep["duration"] - 1.5:
        flags.append("ends_on_episode_ending")        # writers put cliffhangers here
    share = sum(dialogue_share(s, episodes_by_num[s["episode"]]) * seg_len(s)
                for s in promo["segments"]) / max(total_len(promo), 0.01)
    promo["dialogue_share"] = round(share, 2)
    if share < 0.25:
        flags.append("mostly_visual_text_only_judgement_weak")

    promo["duration"] = total_len(promo)
    promo["status"] = status
    promo["flags"] = flags
    return promo


def overlap_fraction(a, b):
    """Share of the SHORTER promo that overlaps the other (single-episode promos only)."""
    if len(a["segments"]) != 1 or len(b["segments"]) != 1:
        return 0.0
    sa, sb = a["segments"][0], b["segments"][0]
    if sa["episode"] != sb["episode"]:
        return 0.0
    inter = min(sa["end"], sb["end"]) - max(sa["start"], sb["start"])
    shorter = min(seg_len(sa), seg_len(sb))
    return max(0.0, inter) / max(shorter, 0.01)


def dedupe(promos, threshold=0.5, key=lambda p: p.get("ai_score", 0)):
    """Keep the best promo; drop others that overlap it by more than `threshold`."""
    kept = []
    for p in sorted(promos, key=key, reverse=True):
        clash = next((k for k in kept if overlap_fraction(p, k) > threshold), None)
        if clash:
            p["status"] = "rejected"
            p["flags"].append(f"duplicate_of_{clash['promo_id']}")
        else:
            kept.append(p)
    return promos