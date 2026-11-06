"""
prompts.py: every instruction we give the AI lives here, in one place.

Keeping prompts out of the logic files means we can improve a prompt
without touching code, and compare prompt versions in the Journey Log.
Placeholders look like <<THIS>> (not {this}) so the JSON braces stay literal.
"""

PROMPT_VERSION = "beats-v1"
STITCH_VERSION = "stitch-v1"
JUDGE_VERSION = "judge-v1"

SYSTEM_EDITOR = (
    "You are a senior promo editor for vertical microdrama apps like ReelShort and DramaBox. "
    "You pick 20-60 second clips from a show that make a scrolling stranger stop, watch, "
    "and tap to see what happens next. You are precise, harsh in scoring, and you only "
    "refer to script rows by the LINE_IDs you are given."
)

# ---------------------------------------------------------------- STEP 3: per-episode beats
BEATS_PROMPT = """You will read ONE episode of a vertical microdrama. Find the best PROMO clips inside it.

A promo is a 20-60 second clip posted on TikTok / Reels / Shorts to pull in NEW viewers who have never seen the show.
A great promo has:
1. HOOK - something in the first 3 seconds that stops a scrolling thumb: a slap or violence, a shocking reveal,
   a cruel or shocking line, a public humiliation, a threat, a dramatic entrance, a forbidden kiss.
2. CLIFFHANGER - it ends on an unresolved moment (a question, a threat, a reveal about to land,
   a decision not yet made). Cut BEFORE the answer.
3. STANDALONE - a stranger understands it. Avoid clips that need names, backstory or earlier episodes.

SERIES PREMISE (episode 1 logline): <<PREMISE>>

THE EPISODE (each row: LINE_ID [start-end] SPEAKER or TYPE: text)
<<EPISODE>>

RULES
- Refer to rows ONLY by the LINE_IDs shown above (e.g. "L012"). Never invent IDs or timestamps.
- start_id = the row where the promo begins. The hook must land within 3 seconds of this row's start,
  so start ON the hook row or at most one short row before it.
- hook_id = the row that contains the hook itself.
- end_id = the last row included; the promo ends when this row ends. Choose a row that leaves a question open.
- Aim for 25-50 seconds from start_id's start to end_id's end (hard limits: 20 to 60 seconds).
- Return 0 to 3 promos. Quality over quantity: a quiet episode may have none.
- Also list up to 6 key MOMENTS (strong hooks and strong cliffhangers, even short ones).
  They are used later to stitch promos across episodes.
- Scores are integers from 1 to 10. Be harsh: 9-10 means you would bet money on it going viral.

Return ONLY JSON in exactly this shape:
{
  "promos": [
    {
      "start_id": "L000",
      "hook_id": "L000",
      "end_id": "L000",
      "hook": "what happens in the first 3 seconds, in plain words",
      "cliffhanger": "the unresolved question the viewer is left with",
      "why": "one line on why this works for a stranger scrolling",
      "hook_type": "slap | violence | reveal | shocking_line | humiliation | threat | romance | entrance | other",
      "hook_score": 0,
      "cliffhanger_score": 0,
      "standalone_score": 0
    }
  ],
  "moments": [
    {"line_id": "L000", "role": "hook | cliffhanger", "summary": "one line", "score": 0}
  ]
}"""


def beats_prompt(premise, episode_text):
    return BEATS_PROMPT.replace("<<PREMISE>>", premise).replace("<<EPISODE>>", episode_text)


# ---------------------------------------------------------------- STEP 4b: cross-episode stitching
STITCH_PROMPT = """You are building MONTAGE promos for a vertical microdrama by joining 2-4 short moments
from DIFFERENT parts of the show into one 20-60 second clip for TikTok / Reels / Shorts.

SERIES PREMISE: <<PREMISE>>

Below are the strongest moments, each with a few rows of context. Row IDs look like "E03:L071"
(episode 3, line 71). Each row: ROW_ID [start-end] SPEAKER or TYPE: text

<<MOMENTS>>

Build <<N>> montage promos. Each promo:
- has 2 to 4 segments; each segment is a continuous run of rows from ONE episode, given by start_id and end_id
  (both from the same episode, start before end). Aim for 6-20 seconds per segment.
- total length of all segments 20-60 seconds.
- segment 1 must START on a hook (stops the scroll in the first 3 seconds).
- the last segment must END on an unresolved cliffhanger. Never include the answer.
- tells ONE clear mini-story a stranger can follow (e.g. humiliation -> mysterious rescuer -> threat).
- prefer moments from early episodes (new viewers start at episode 1) and avoid giving away late twists.
- use ONLY row IDs shown above. Never invent IDs or timestamps.

Return ONLY JSON:
{
  "promos": [
    {
      "segments": [{"start_id": "E01:L026", "end_id": "E01:L040"}],
      "hook_id": "E01:L027",
      "hook": "what happens in the first 3 seconds",
      "cliffhanger": "the unresolved question at the end",
      "why": "one line on why this montage works for a stranger",
      "hook_type": "slap | violence | reveal | shocking_line | humiliation | threat | romance | entrance | other"
    }
  ]
}"""


def stitch_prompt(premise, moments_text, n):
    return (STITCH_PROMPT.replace("<<PREMISE>>", premise)
            .replace("<<MOMENTS>>", moments_text).replace("<<N>>", str(n)))


# ---------------------------------------------------------------- STEP 5: independent judge
SYSTEM_JUDGE = (
    "You are a strict growth marketer judging short-form video promos for a microdrama app. "
    "You have NEVER seen this show. You judge only what is inside the clip you are shown."
)

JUDGE_PROMPT = """Here is the full script of ONE promo clip, exactly as a stranger would see it on TikTok.
Times are seconds from the start of the clip. Rows: [+time] SPEAKER or TYPE: text
(CAMERA / ACTION rows describe what is on screen.)

<<CLIP>>

Score it like a harsh reviewer (integers 1-10; 5 = average, 8 = clearly strong, 10 = exceptional):
- hook: do the first 3 seconds (rows at +0.0s to +3.0s) stop a scrolling thumb?
- cliffhanger: does it END on an open question that makes you need the next episode?
- standalone: can a stranger follow who is who and what is at stake, with no backstory?
- overall: would you post this as a paid ad?
Also answer:
- resolved_inside: true if the clip shows the answer to its own main question before it ends (a weak ending).
- confusing: true if a stranger would be lost (unclear characters, missing setup).
- one_line_verdict: one sentence.
- fix: one concrete suggestion (e.g. "end 4s earlier on the threat", "start on the slap"), or "" if none.

Return ONLY JSON:
{"hook": 0, "cliffhanger": 0, "standalone": 0, "overall": 0,
 "resolved_inside": false, "confusing": false, "one_line_verdict": "", "fix": ""}"""


def judge_prompt(clip_text):
    return JUDGE_PROMPT.replace("<<CLIP>>", clip_text)