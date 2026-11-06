# App design spec (decided before writing code)

## Who uses it
1. Kuku editor: "Which promos do I post, and can I trust them?"
2. Interviewer: "Does it work, and how do you know it's good?"

## Decisions
| Area | Choice |
|---|---|
| Layout | **Editor inbox**: ranked promo list on the left, selected promo's details on the right |
| Style | **Dark studio**: dark background, one accent colour, like a video-editing tool |
| Clip view | **Highlighted timeline**: bar showing where the clip sits in the episode; script rows with times; HOOK (first 3s) and CLIFFHANGER (last line) highlighted |
| Extras | Quality page · Approve/Reject + export · Run on a new show · Compare two models |

## Pages (sidebar navigation)
1. **Inbox** (main)
   - Left: ranked list; filter = Post first / All / Needs review / Approved / Rejected
   - Right: promo header (id, segments, length, score), hook, cliffhanger, why,
     episode timeline bar, highlighted script, judge scores + verdict + suggested fix,
     score breakdown, rule flags, buttons [Approve] [Reject]
   - Export: download approved promos as CSV
2. **Quality**: gold set (4/5, end gap 1.4s), audit (79/79), tests (13/13), stability (4/4),
   second judge (red flags 15/16, Spearman 0.38), read from outputs/final/*.md
3. **Run on a new show**: upload scripts .zip + visitor's OWN API key (never saved), choose provider/models,
   episode limit, workers -> runs the full pipeline -> opens the result in the Inbox
4. **Compare models**: load two finished runs of the same show (e.g. Gemini picker vs gpt-oss picker)
   and compare overlap of picks + top-10 side by side (no live double run, to save time and cost)

## Rules
- Ships with NO Kuku scripts/results; everything comes from local outputs/ or uploads.
- The visitor's key is used only for that run, then removed from memory.
- Approve/Reject lives in the browser session; the export is the record.

## Done = checklist (verify after building)
- [ ] Inbox loads the local run; all 79 promos listed; filters work
- [ ] Clip view: timeline bar + hook/cliffhanger highlighted correctly for single AND montage promos
- [ ] Approve/Reject persists while clicking around; export contains only approved
- [ ] Quality page shows all 5 checks with the same numbers as the files
- [ ] Run page works on a 2-episode test with own key; key not left in os.environ
- [ ] Compare page works with two runs
- [ ] Dark theme applied; readable
- [ ] No Kuku data in the GitHub repo
