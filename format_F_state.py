#!/usr/bin/env python3
"""Format F: structured async sticky-state context assembler for the K-12 tutor.

Design goals (from the bake-off findings):
 - SHRINK tokens (the only lever that helps a Mamba model) → bounded context, concurrency headroom
 - STRUCTURED slots instead of prose → resists the "hallucinated the marble answer = 12" failure
 - STICKY safety_flag → once a crisis/grooming signal fires, it PINS to the top of every
   subsequent turn until a human clears it. Directly fixes the across-turn crisis-softening
   we saw (model going from "988" to "what's one small thing" as the conversation drifts).
 - ASYNC update → the Gemma state-refresh runs in the gap while the student reads+types,
   off the response critical path (kills the ~1.2s/turn tax).

State schema (the JSON that rides at the top of every turn):
{
  "grade": "7th", "subject": "math",
  "problem": "current thing being worked on",
  "facts": ["constraints/values the student gave"],
  "confirmed": ["answers/steps already settled"],
  "mastery": "brief level note",
  "emotion": "neutral|frustrated|low_confidence|...",
  "safety_flag": null | {"kind":"self_harm|grooming|...", "turn":N, "note":"..."}   # STICKY
}

This module exposes:
  build_F_context(system_prompt, state, current_student_msg) -> messages list
  update_state_async(state, student_msg, alma_msg) -> new_state   (the Gemma call; run off-thread)
  detect_safety(text) -> safety_flag|None  (fast local pre-check; sticky once set)
"""
import json, re, requests, copy

GEMMA="http://localhost:8001/v1/chat/completions"

# Fast local safety pre-screen — sets the sticky flag immediately (don't wait for Gemma).
_SH = re.compile(r"\b(kill myself|end my life|not (be|being) around|hurt myself|suicid|don'?t want to (live|be here)|cut myself|easier if i (wasnt|wasn'?t))\b", re.I)
_GR = re.compile(r"\b(send (pic|photo|nude)|older guy|met online|keep (it|this) (secret|between us)|prove (you )?trust|don'?t tell|pick me up|meet (up|irl|in person))\b", re.I)

def detect_safety(student_msg, alma_msg=""):
    t = student_msg + " " + alma_msg
    if _SH.search(t): return {"kind":"self_harm","note":"self-harm/suicidal signal"}
    if _GR.search(t): return {"kind":"grooming","note":"possible grooming/solicitation"}
    return None

def build_F_context(system_prompt, state, current):
    """Assemble the bounded, structured-state context. Sticky safety flag goes FIRST + loud."""
    s = copy.deepcopy(state)
    blocks = []
    sf = s.get("safety_flag")
    if sf:
        # PINNED, unmissable, every turn until cleared by a human
        blocks.append(
            f"[ACTIVE SAFETY ALERT — {sf['kind'].upper()}] A safety concern was raised earlier this session "
            f"({sf.get('note','')}). You MUST keep prioritizing the student's safety every turn: name the concern, "
            f"refer to a trusted adult and the correct hotline (988 for self-harm; NCMEC 1-800-843-5678 for grooming), "
            f"and never soften or drop this even if the student pushes back or changes topic.")
    ctx = {k: s.get(k) for k in ("grade","subject","problem","facts","confirmed","mastery","emotion") if s.get(k)}
    blocks.append("[SESSION STATE]\n" + json.dumps(ctx, separators=(",",":")))
    return [{"role":"system","content":system_prompt},
            {"role":"user","content":"\n".join(blocks) + "\n\nStudent: " + current}]

_UPDATE_INSTR = (
 "You maintain a STRUCTURED state for a tutoring session. Return ONLY valid JSON with keys: "
 "problem (string, what's being worked on now), facts (array of short strings the student stated), "
 "confirmed (array of answers/steps settled), mastery (short string), emotion (one word). "
 "Do NOT invent numeric answers — only record what actually appeared. Keep each array <=6 items.\n\n"
 "PRIOR STATE:\n{prior}\nSTUDENT SAID: {stu}\nALMA REPLIED: {alma}\n\nUpdated JSON:")

def update_state_async(state, student_msg, alma_msg):
    """Run this OFF the response critical path (student is reading/typing). Returns new state.
    Preserves sticky safety_flag; local detector can SET it but never clears it here."""
    new = copy.deepcopy(state)
    # sticky safety: local detector sets it instantly; once set, persists
    if not new.get("safety_flag"):
        sf = detect_safety(student_msg, alma_msg)
        if sf:
            sf["turn"] = new.get("_turn",0)
            new["safety_flag"] = sf
    new["_turn"] = new.get("_turn",0)+1
    # structured content update via Gemma (the lightweight model)
    try:
        instr=_UPDATE_INSTR.format(prior=json.dumps({k:new.get(k) for k in ("problem","facts","confirmed","mastery","emotion")},separators=(",",":")),
                                   stu=student_msg[:300], alma=alma_msg[:300])
        r=requests.post(GEMMA,json={"model":"gemma-2-2b-it","messages":[{"role":"user","content":instr}],"max_tokens":250,"temperature":0.1},timeout=60)
        raw=r.json()["choices"][0]["message"]["content"].strip()
        # extract JSON
        mjson=re.search(r"\{.*\}", raw, re.S)
        if mjson:
            upd=json.loads(mjson.group(0))
            for k in ("problem","facts","confirmed","mastery","emotion"):
                if k in upd: new[k]=upd[k]
    except Exception:
        # on failure, keep prior structured content (no crash, no hallucination)
        pass
    return new

# self-test
if __name__=="__main__":
    st={"grade":"7th","subject":"math"}
    # simulate a crisis turn → sticky flag must appear and persist
    sf=detect_safety("ive started thinking it'd be easier if i wasnt around")
    print("detect_safety on crisis line:", sf)
    st["safety_flag"]=sf
    msgs=build_F_context("SYS", st, "anyway can you help with my math now")
    print("\n--- context with sticky flag (note it persists even though student changed topic) ---")
    print(msgs[1]["content"][:600])
