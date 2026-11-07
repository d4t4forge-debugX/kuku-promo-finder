"""
app.py: the Promo Finder web app (Streamlit). Design "C: table first" from APP_DESIGN.md.

Pages (sidebar):
  Promos            table of ranked promos + episode coverage strip + the selected promo's details,
                    approve / reject with a reason, timecode + decisions exports
  Quality           headline numbers of the cross-checks + known limits
  Run on a new show upload a scripts .zip + YOUR OWN API key -> runs src/pipeline.run_pipeline()
  Compare models    two finished runs of the same show side by side

Privacy: the app ships with NO Kuku scripts and NO Kuku results. It shows local outputs/, uploaded files,
or the bundled demo/ show, which is made up (not Kuku content).
The calculations live in src/app_logic.py (tested); this file only draws the screen.

Run:  streamlit run app.py
"""
import html
import json
import os
import tempfile
from pathlib import Path

import streamlit as st

from src import app_logic as L
from src.parser import load_show, timecode

st.set_page_config(page_title="Promo Finder", page_icon="🎬", layout="wide")

st.markdown("""
<style>
.pf-card  {background:#161A23;border:1px solid #262C3A;border-radius:12px;padding:14px 16px;margin-bottom:10px}
.pf-hook  {background:#2A2112;border:1px solid #5A4419;border-radius:12px;padding:12px 14px}
.pf-cliff {background:#142033;border:1px solid #2D4A75;border-radius:12px;padding:12px 14px}
.pf-lbl   {font-size:12px;font-weight:700;letter-spacing:.5px;margin-bottom:4px}
.pf-strip {display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));gap:3px;margin:4px 0 2px}
.pf-cell  {height:18px;border-radius:3px}
.pf-post  {background:#F2A93B} .pf-has {background:#3B5B8C} .pf-none {background:#232838;border:1px solid #3A4256}
.pf-bar   {position:relative;height:12px;background:#232838;border-radius:999px;margin:4px 0 10px}
.pf-seg   {position:absolute;top:0;bottom:0;background:#F2A93B;border-radius:999px}
.pf-row   {display:flex;gap:10px;padding:5px 8px;border-radius:8px;font-size:14px;line-height:1.45}
.pf-row.zone {background:#1F1A10} .pf-row.hook {background:#2A2112} .pf-row.cliff {background:#142033}
.pf-t     {font-family:monospace;color:#A3ACBC;min-width:54px}
.pf-who   {font-weight:600;white-space:nowrap}
.pf-dim   {color:#A3ACBC}
.pf-tag   {margin-left:auto;font-size:11px;font-weight:700;border-radius:999px;padding:1px 8px;color:#0E1014;white-space:nowrap;flex-shrink:0;align-self:flex-start}
.pf-scroll {max-height:520px;overflow-y:auto}
.pf-div   {font-size:12px;color:#7AB0FF;padding:8px 8px 2px;font-weight:600}
</style>
""", unsafe_allow_html=True)

esc = html.escape


# ------------------------------------------------------------------ loading
@st.cache_data(show_spinner=False)
def episodes_from_zip(zip_bytes):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "show.zip"
        path.write_bytes(zip_bytes)
        return {e["episode"]: e for e in load_show(path)}


@st.cache_data(show_spinner=False)
def episodes_from_folder(folder):
    return {e["episode"]: e for e in load_show(folder)}


def sidebar_run_picker():
    """Pick a finished run (local) or upload one; optionally a scripts zip to read each clip."""
    runs = L.find_runs()
    names = [r.name.removesuffix("_ranked.json") for r in runs]
    data = None
    if names:
        default = names.index(st.session_state["last_run"]) if st.session_state.get("last_run") in names else 0
        choice = st.sidebar.selectbox("Run", names, index=default)
        data = json.loads(runs[names.index(choice)].read_text())
    uploaded = st.sidebar.file_uploader("…or upload a *_ranked.json", type=["json"])
    if uploaded:
        data = json.load(uploaded)
    scripts = st.sidebar.file_uploader("Scripts .zip (optional, to read clips)", type=["zip"])
    episodes = None
    if scripts:
        episodes = episodes_from_zip(scripts.getvalue())
    elif data:
        src = data.get("source", data["show"])
        for folder in (Path("data/raw") / src, Path("demo") / src):   # local scripts, else the made-up demo
            if folder.exists():
                episodes = episodes_from_folder(str(folder))
                break
    return data, episodes


# ------------------------------------------------------------------ small HTML pieces
def coverage_html(data):
    cells = "".join(f'<div class="pf-cell pf-{c["kind"]}" title="Episode {c["ep"]}: {c["kind"]}"></div>'
                    for c in L.coverage(data))
    n = len(L.episode_numbers(data))
    return (f'<div class="pf-dim" style="font-size:12px">Episode coverage ({n} episodes): '
            f'<span style="color:#F2A93B">■</span> in post-first list · <span style="color:#3B5B8C">■</span> has promos · '
            f'<span style="color:#3A4256">■</span> none found</div>'
            f'<div class="pf-strip" style="--n:{n}">{cells}</div>')


def timeline_html(p, data):
    out = ""
    for seg in L.timeline(p, data):
        out += (f'<div class="pf-dim" style="font-size:12px">Episode {seg["ep"]} (length {seg["length"]})</div>'
                f'<div class="pf-bar"><div class="pf-seg" style="left:{seg["left"]}%;width:{seg["width"]}%"></div></div>')
    return out


def script_html(p, episodes):
    out = []
    for r in L.clip_rows(p, episodes):
        if "divider" in r:
            out.append(f'<div class="pf-div">{esc(r["divider"])}</div>')
            continue
        tag = {"hook": '<span class="pf-tag" style="background:#F2A93B">HOOK</span>',
               "cliff": '<span class="pf-tag" style="background:#7AB0FF">CLIFFHANGER</span>'}.get(r["tag"], "")
        who_cls = "pf-who pf-dim" if r["kind"] != "dialogue" else "pf-who"
        emo = f' <span class="pf-dim">({esc(r["emotion"])})</span>' if r["emotion"] else ""
        out.append(f'<div class="pf-row {r["tag"]}"><span class="pf-t">+{r["t"]:.1f}s</span>'
                   f'<span class="{who_cls}">{esc(r["who"])}{emo}</span><span>{esc(r["text"])}</span>{tag}</div>')
    return "".join(out)


# ------------------------------------------------------------------ page: promos
def page_promos(data, episodes):
    ranked, show = data["ranked"], data["show"]
    decisions = st.session_state.setdefault("decisions", {}).setdefault(show, {})

    st.title(f"Promos · {show}")
    st.caption(f"Picker `{data.get('picker_model', '?')}` · Judge `{data.get('judge_model', '?')}` · "
               "timecodes are HH:MM:SS:FF at an assumed 30 fps")
    approved = sum(d["status"] == "approved" for d in decisions.values())
    rejected = sum(d["status"] == "rejected" for d in decisions.values())
    m = st.columns(4)
    m[0].metric("Ranked promos", len(ranked))
    m[1].metric("Need human review", sum(bool(p["review_reasons"]) for p in ranked))
    m[2].metric("Approved", approved)
    m[3].metric("Rejected", rejected)

    d1, d2 = st.columns(2)
    d1.download_button("⬇ Timecode cut list (all ranked, CSV)", L.timecode_csv(ranked),
                       file_name=f"{show}_timecodes.csv", width="stretch")
    d2.download_button("⬇ My decisions + reasons (CSV)", L.decisions_csv(ranked, decisions),
                       file_name=f"{show}_decisions.csv", disabled=not decisions, width="stretch")

    st.markdown(coverage_html(data), unsafe_allow_html=True)

    chosen = st.radio("Show", L.FILTERS, horizontal=True, label_visibility="collapsed")
    promos = L.filter_promos(ranked, chosen, decisions)
    if chosen == "Post first":
        st.caption("Episodes 1-15, no red flags. A new viewer who taps a promo starts at Episode 1, so these match "
                   "what they will watch next. No back-to-back repeats of episode or hook type.")
    if not promos and chosen == "Post first" and ranked:
        st.info("No promo in episodes 1-15 passed without a review flag, so nothing is safe to auto-post. "
                "Open **Needs review** to see the flagged candidates and why.")
    elif not promos:
        st.info("Nothing here yet.")
        return

    event = st.dataframe(L.table_rows(promos, decisions), hide_index=True, width="stretch",
                         on_select="rerun", selection_mode="single-row", key=f"table_{show}_{chosen}",
                         column_config={"Hook": st.column_config.TextColumn(width="large"),
                                        "Score": st.column_config.NumberColumn(format="%.2f")})
    rows = event.selection.rows if event and event.selection else []
    p = promos[rows[0]] if rows else promos[0]
    if not rows:
        st.caption("Click a row to open it. Showing the first one.")
    promo_detail(p, data, episodes, decisions)


def promo_detail(p, data, episodes, decisions):
    pid, j = p["promo_id"], p.get("judge", {})
    with st.container(border=True):
        left, right = st.columns([3, 2], gap="large")
        with left:
            badge = " · ⚠ spoiler risk (late episode)" if p.get("spoiler_risk") else ""
            st.subheader(f"{pid} · {p['duration']}s · score {p['final_score']}{badge}")
            for s in p["segments"]:
                st.markdown(f"**Episode {s['episode']}** `{s['start_ts']} → {s['end_ts']}` · "
                            f"timecode `{timecode(s['start'])} → {timecode(s['end'])}`")
            st.markdown(timeline_html(p, data), unsafe_allow_html=True)
            h, c = st.columns(2)
            h.markdown(f'<div class="pf-hook"><div class="pf-lbl" style="color:#F2A93B">HOOK · FIRST 3 SECONDS</div>'
                       f'{esc(p["hook"])}</div>', unsafe_allow_html=True)
            c.markdown(f'<div class="pf-cliff"><div class="pf-lbl" style="color:#7AB0FF">CLIFFHANGER · WHERE IT CUTS</div>'
                       f'{esc(p["cliffhanger"])}</div>', unsafe_allow_html=True)
            st.markdown(f"**Why it works:** {p['why']}")
            st.markdown("**The clip as a viewer sees it**")
            if episodes:
                st.markdown(f'<div class="pf-card pf-scroll">{script_html(p, episodes)}</div>', unsafe_allow_html=True)
            else:
                st.info("Upload the scripts .zip in the sidebar to read this clip here.")
        with right:
            st.markdown("**Independent judge** (sees only the clip, like a stranger)")
            k = st.columns(4)
            for col, key, label in zip(k, ("hook", "cliffhanger", "standalone", "overall"),
                                       ("Hook", "Cliff", "Alone", "Overall")):
                col.metric(label, j.get(key, "–"))
            if j.get("one_line_verdict"):
                st.markdown(f"_{j['one_line_verdict']}_")
            if j.get("fix"):
                st.markdown(f"**Suggested fix:** {j['fix']}")
            if p["review_reasons"]:
                st.warning("Needs a human look: " + ", ".join(r.replace("_", " ") for r in p["review_reasons"]))
            with st.expander("Why this rank"):
                st.table([{"part": k2, "points": v} for k2, v in p.get("score_parts", {}).items()])
                st.caption("Rule-check flags: " + (", ".join(p["flags"]) or "none"))

            st.divider()
            current = decisions.get(pid)
            if current:
                extra = f" ({current['reason']})" if current.get("reason") else ""
                st.success(f"Decision: {current['status']}{extra}")
                if st.button("Undo decision", key=f"undo_{pid}", width="stretch"):
                    decisions.pop(pid)
                    st.rerun()
            if st.button("✓ Approve", key=f"ok_{pid}", type="primary", width="stretch"):
                decisions[pid] = {"status": "approved"}
                st.rerun()
            reason = st.selectbox("Reject reason", L.REJECT_REASONS, key=f"reason_{pid}")
            note = st.text_input("Note (optional)", key=f"note_{pid}")
            if st.button("✗ Reject", key=f"no_{pid}", width="stretch"):
                decisions[pid] = {"status": "rejected", "reason": reason, "note": note}
                st.rerun()


# ------------------------------------------------------------------ page: quality
def page_quality(data):
    st.title("How we know it's good")
    st.write("Every number comes from a real run of the eval scripts (`eval/`). "
             "Each check is independent of the code it checks.")
    src = data.get("source", data["show"]) if data else "broken_soldier"
    q = L.read_quality(src)
    if not any(v.get("values") for v in q.values()) and src != "broken_soldier":
        q = L.read_quality("broken_soldier")   # eval checks exist only for the full input pack
        st.info(f"No quality checks were run on `{src}`. Showing the checks from the full input pack "
                "(broken_soldier, 50 episodes): the blind gold set exists only for that show.")
    cards = [("Blind human gold set", "gold", lambda v: v[0], lambda v: f"human picks found · endings within {v[1]}s"),
             ("Independent audit", "audit", lambda v: v[0], lambda v: "promos pass 7 checks vs raw scripts"),
             ("Stability (run twice)", "stability", lambda v: v[0], lambda v: "same promos picked again"),
             ("Second judge (other company)", "judge", lambda v: v[0], lambda v: f"rank agreement · red flags agree {v[1]}")]
    cols = st.columns(4)
    for col, (title, key, big, note) in zip(cols, cards):
        v = q.get(key, {}).get("values")
        col.metric(title, big(v) if v else "not run")
        col.caption(note(v) if v else "run the matching eval script")
    st.caption("Automated tests: run `python -m pytest` (parser, AI-answer handling, every rule, eval maths).")

    st.subheader("Known limits")
    st.markdown("""
- Reads **text only**: a purely visual hook (a look, a silent gesture) is under-rated (flagged *mostly_visual*).
- **Long episodes** can hold more good promos than the 2-3 it returns.
- **Endings that answer their own question** slip through the picker; the judge flags them for review.
- **Which good promo is best is taste**: the two judges agree on red flags but only moderately on the middle ranks,
  so an editor makes the final call.
- Script timestamps are **assumed to match the final edit**.
""")
    for key, label in (("gold", "Gold set details"), ("audit", "Audit details"),
                       ("stability", "Stability details"), ("judge", "Judge agreement details")):
        if key in q:
            with st.expander(label):
                st.markdown(q[key]["text"])


# ------------------------------------------------------------------ page: run
def page_run():
    from src.pipeline import run_pipeline   # imported here so the other pages load fast

    st.title("Run on a new show")
    st.write("Upload a .zip of episode scripts (one .txt per episode, same format as the input pack). "
             "Use **your own** API key: it is used for this run only and is never saved.")
    zip_file = st.file_uploader("Scripts .zip", type=["zip"])
    c1, c2 = st.columns(2)
    provider = c1.selectbox("Provider", ["gemini", "groq", "openai", "anthropic"])
    api_key = c2.text_input("Your API key", type="password")
    c3, c4 = st.columns(2)
    picker = c3.text_input("Picker model (fast)", "gemini-3.8-flash")
    judge = c4.text_input("Judge model (stronger)", "gemini-3.1-pro-preview")
    c5, c6, c7 = st.columns(3)
    limit = c5.number_input("Only first N episodes (0 = all)", min_value=0, value=0)
    workers = c6.number_input("Parallel AI calls", min_value=1, max_value=8, value=4,
                              help="Lower this if you hit rate limits (429).")
    tag = c7.text_input("Run tag (optional)", help="Keeps a second run of the same show separate, e.g. 'gptoss'.")
    stitch = st.checkbox("Include cross-episode montages", value=True)

    if not st.button("Run", type="primary", disabled=not (zip_file and api_key)):
        return
    src = Path(tempfile.gettempdir()) / Path(zip_file.name).name.replace(" ", "_")
    src.write_bytes(zip_file.getvalue())
    key_name = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY",
                "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}[provider]
    names = ["LLM_PROVIDER", "LLM_MODEL", "JUDGE_MODEL", "RUN_TAG", key_name]
    saved = {k: os.environ.get(k) for k in names}
    os.environ.update({"LLM_PROVIDER": provider, "LLM_MODEL": picker, "JUDGE_MODEL": judge,
                       "RUN_TAG": tag.strip(), key_name: api_key})
    try:
        with st.status("Running the pipeline...", expanded=True) as status:
            out = run_pipeline(src, workers=int(workers), stitch=stitch, limit=int(limit) or None,
                               step=lambda msg: status.write(msg))
            status.update(label="Done", state="complete")
        st.session_state["last_run"] = out["show"]
        st.success(f"Finished `{out['show']}`. Open **Promos** in the sidebar to review it. Tokens: {out['usage']}")
        d1, d2, d3 = st.columns(3)
        d1.download_button("ranked.json", Path(out["ranked"]).read_text(), file_name=Path(out["ranked"]).name)
        d2.download_button("report.md", Path(out["report"]).read_text(), file_name=Path(out["report"]).name)
        d3.download_button("timecodes.csv", Path(out["timecodes"]).read_text(), file_name=Path(out["timecodes"]).name)
    except Exception as e:
        st.error(f"Run failed: {type(e).__name__}: {e}")
    finally:
        for k, v in saved.items():           # take the visitor's key back out of memory
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ------------------------------------------------------------------ page: compare
def page_compare():
    st.title("Compare models")
    runs = L.find_runs()
    if len(runs) < 2:
        st.info("Needs two finished runs of the same show. Make a second one with another picker model, e.g.:\n\n"
                "`RUN_TAG=gptoss LLM_PROVIDER=groq LLM_MODEL=openai/gpt-oss-120b "
                "python run.py data/raw/broken_soldier --limit 10`")
        return
    names = [r.name.removesuffix("_ranked.json") for r in runs]
    c1, c2 = st.columns(2)
    a_name = c1.selectbox("Run A", names, index=0)
    b_name = c2.selectbox("Run B", names, index=1)
    a = json.loads(runs[names.index(a_name)].read_text())
    b = json.loads(runs[names.index(b_name)].read_text())
    r = L.compare_runs(a, b)
    st.caption(f"A: picker `{a.get('picker_model', '?')}` · B: picker `{b.get('picker_model', '?')}` · "
               f"compared on episodes 1-{r['episodes_compared']} (covered by both runs)")
    m = st.columns(3)
    m[0].metric("Promos found by both", r["found_by_both"])
    m[1].metric("Only in A", r["only_a"])
    m[2].metric("Only in B", r["only_b"])
    t1, t2 = st.columns(2)
    for col, label, rows in ((t1, f"Top 5 · {a_name}", r["top_a"]), (t2, f"Top 5 · {b_name}", r["top_b"])):
        col.markdown(f"**{label}**")
        col.dataframe([{"Promo": x["id"], "Timecodes": x["seg"], "Score": x["score"],
                        "In both runs": "yes" if x["both"] else "only here"} for x in rows],
                      hide_index=True, width="stretch")


# ------------------------------------------------------------------ layout
st.sidebar.markdown("## 🎬 Promo Finder")
page = st.sidebar.radio("Page", ["Promos", "Quality", "Run on a new show", "Compare models"],
                        label_visibility="collapsed")
st.sidebar.divider()

if page in ("Promos", "Quality"):
    data, episodes = sidebar_run_picker()
    if page == "Promos":
        if data:
            page_promos(data, episodes)
        else:
            st.title("Promo Finder")
            st.info("No finished run found. Upload a `<show>_ranked.json` in the sidebar, "
                    "or create one on **Run on a new show**.")
    else:
        page_quality(data)
elif page == "Run on a new show":
    page_run()
else:
    page_compare()