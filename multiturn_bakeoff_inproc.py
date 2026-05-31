#!/usr/bin/env python3
"""Multi-turn context-format bake-off — IN-PROCESS BF16 (safe; no touch of prod FP8 :8000).

Loads BF16 base once + a LoRA, walks each trajectory turn-by-turn under a chosen
context FORMAT, generates the real Alma reply, regenerates the Gemma running-summary
(HTTP :8001) after each reply for summary formats. Captures full transcript +
per-turn context size (for latency analysis) for human grading.

Usage: python3 multiturn_bakeoff_inproc.py <traj.jsonl> <A|B|D> <lora_dir> <label> <out.jsonl>
Run with: /home/admin/miniconda3/envs/unsloth/bin/python3  CUDA_VISIBLE_DEVICES=1
"""
import os, sys, json, time, requests
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF","expandable_segments:True")
os.environ.setdefault("TOKENIZERS_PARALLELISM","false")

TRAJ, FMT, LORA_DIR, LABEL, OUT = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
BASE = "/mnt/models/soul/models/nemotron-3-nano-omni-bf16"
GEMMA_URL = "http://localhost:8001/v1/chat/completions"
RECENT_PAIRS, TUTOR_CAP, STUDENT_CAP = 6, 300, 500

SYS = ("You are Alma, a warm and curious Socratic tutor for students ages 5-18. "
  "For concepts: brief clear answer then a curious follow-up. For homework: guide step-by-step, never give the final answer. "
  "ALWAYS end with a curiosity-sparking question. Conversational, under ~80 words. "
  "Student safety is the non-negotiable top priority; when safety and helpfulness conflict, safety wins — decline explicitly first, then optionally offer a safer path. "
  "If a student shows distress, name it and refer to a trusted adult or hotline. Crisis: 988. Grooming: NCMEC 1-800-843-5678. "
  "You are based on a modified NVIDIA model.")

def cap_tutor(t, cap=TUTOR_CAP):
    t=(t or "").strip()
    if len(t)<=cap: return t
    cut=t[:cap]; b=max(cut.rfind('.'),cut.rfind('\n'))
    if b>cap//2: cut=cut[:b+1]
    return cut.strip()+" [...]"

def gemma_summary(prior, stu, alma, grade, subject):
    instr=("You maintain a running summary of a tutoring session for the next turn. "
      "Update it to include what just happened. Under 120 words, factual, both sides. "
      "Track: what the student is working on, facts they gave, apparent mastery/struggles, emotional state, any safety concern.\n\n"
      f"PRIOR SUMMARY:\n{prior or '(none — session start)'}\n\nSTUDENT JUST SAID: {stu}\nALMA JUST REPLIED: {alma}\n\nNew running summary:")
    try:
        r=requests.post(GEMMA_URL,json={"model":"gemma-2-2b-it","messages":[{"role":"user","content":instr}],"temperature":0.2,"max_tokens":200},timeout=60)
        r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return (prior or "")+f" | turn: {stu[:60]}"

def msgs_A(history,current):
    out=[{"role":"system","content":SYS}]; win=RECENT_PAIRS*2
    if len(history)>win:
        older=history[:-win]; parts=[]
        for m in older:
            if m["role"]=="user": parts.append(f"- Student asked: {m['content'][:200]}")
            else:
                c=m["content"][:100].replace("\n"," ").strip()
                if len(m["content"])>100: c+="..."
                parts.append(f"- Alma answered: {c}")
        summ="\n".join(parts)
        if len(summ)>2000:
            while len(summ)>2000 and parts: parts.pop(0)
            summ="[...earlier omitted...]\n"+"\n".join(parts)
        out.append({"role":"user","content":f"[Earlier in this conversation]\n{summ}"}); recent=history[-win:]
    else: recent=history
    for m in recent:
        out.append({"role":"user","content":m["content"][:STUDENT_CAP]} if m["role"]=="user" else {"role":"assistant","content":cap_tutor(m["content"])})
    out.append({"role":"user","content":current}); return out

def msgs_B(summary,current,grade,subject):
    d=f"[SESSION CONTEXT]\ngrade: {grade}\nsubject: {subject}\nrunning_summary: {summary or '(session start)'}\n[END CONTEXT]"
    return [{"role":"system","content":SYS},{"role":"user","content":d+"\n\nStudent: "+current}]

def msgs_D(summary,history,current,grade,subject):
    d=f"[SESSION CONTEXT]\ngrade: {grade}\nsubject: {subject}\nrunning_summary: {summary or '(session start)'}\n[END CONTEXT]"
    out=[{"role":"system","content":SYS},{"role":"user","content":d}]
    for m in history[-2:]:
        out.append({"role":"user","content":m["content"][:STUDENT_CAP]} if m["role"]=="user" else {"role":"assistant","content":cap_tutor(m["content"],400)})
    out.append({"role":"user","content":current}); return out

def main():
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel
    print(f"[load base] {LABEL} {FMT}",flush=True); t0=time.time()
    tok=AutoTokenizer.from_pretrained(LORA_DIR,trust_remote_code=True)
    if tok.pad_token_id is None: tok.pad_token=tok.eos_token
    if not getattr(tok,'chat_template',None):
        with open(f"{BASE}/chat_template.jinja") as f: tok.chat_template=f.read()
    base=AutoModelForCausalLM.from_pretrained(BASE,torch_dtype="auto",device_map="auto",trust_remote_code=True,attn_implementation="eager")
    inner=base.language_model if hasattr(base,"language_model") else base
    if hasattr(base,"language_model"): base.language_model=None
    DEV=next(inner.parameters()).device
    model=PeftModel.from_pretrained(inner,LORA_DIR); model.eval()
    print(f"[ready] {time.time()-t0:.0f}s",flush=True)

    def gen(messages):
        try: text=tok.apply_chat_template(messages,enable_thinking=False,tokenize=False,add_generation_prompt=True)
        except: text=tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
        enc=tok(text,return_tensors="pt"); ids=enc["input_ids"].to(DEV); mask=enc.get("attention_mask")
        if mask is not None: mask=mask.to(DEV)
        with torch.no_grad():
            o=model.generate(ids,attention_mask=mask,max_new_tokens=350,do_sample=True,temperature=0.3,top_p=0.9,
                             pad_token_id=tok.eos_token_id,eos_token_id=tok.eos_token_id,
                             tokenizer=tok,stop_strings=["\nuser\n","\n\nuser\n","<|im_end|>","</s>","\nStudent:"])
        return tok.decode(o[0][ids.shape[1]:],skip_special_tokens=True).strip()

    trajs=[json.loads(l) for l in open(TRAJ) if l.strip()]
    out=open(OUT,"w")
    for tj in trajs:
        sid=tj["id"]; grade=tj.get("grade_hint",tj.get("grade","")); subject=tj.get("subject","")
        st=tj["student_turns"] if "student_turns" in tj else [t["content"] for t in tj.get("turns",[]) if t.get("role")=="user"]
        history=[]; summary=""; transcript=[]
        for i,stu in enumerate(st):
            m = msgs_A(history,stu) if FMT=="A" else (msgs_B(summary,stu,grade,subject) if FMT=="B" else msgs_D(summary,history,stu,grade,subject))
            ctx=sum(len(x["content"]) for x in m); t1=time.time()
            try: alma=gen(m)
            except Exception as e: alma=f"[ERR] {e}"
            transcript.append({"turn":i+1,"student":stu,"alma":alma,"gen_s":round(time.time()-t1,1),"ctx_chars":ctx})
            history += [{"role":"user","content":stu},{"role":"assistant","content":alma}]
            if FMT in ("B","D"): summary=gemma_summary(summary,stu,alma,grade,subject)
        out.write(json.dumps({"id":sid,"format":FMT,"label":LABEL,"kind":tj.get("kind",tj.get("archetype","")),
                              "subject":subject,"grade":grade,"final_summary":summary,"transcript":transcript})+"\n"); out.flush()
        print(f"  {sid} done ({len(st)} turns, avg ctx {sum(t['ctx_chars'] for t in transcript)//len(transcript)}ch)",flush=True)
    out.close(); print(f"DONE -> {OUT}",flush=True)

if __name__=="__main__": main()
