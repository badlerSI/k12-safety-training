#!/usr/bin/env python3
"""H: concurrency sweep. The ACTUAL question — how many simultaneous students
before per-turn latency degrades, and does token-reduction (summary) raise the ceiling.

For each concurrency level N in [1,4,8,16,32]:
  - spawn N concurrent "students" each replaying a multi-turn trajectory
  - format A (raw replay, grows) vs F (structured compact state, bounded)
  - measure per-turn latency distribution + aggregate throughput (turns/sec)
Read-only against live FP8 :8000. Box is idle.

Usage: python3 concurrency_H.py <A|F> <out.json>
"""
import json, time, sys, threading, queue, requests, statistics as st
TUTOR="http://localhost:8000/v1/chat/completions"
MODEL="nano-omni"
FMT=sys.argv[1]; OUT=sys.argv[2]
LEVELS=[1,4,8,16,32]
RECENT_PAIRS,TUTOR_CAP,STUDENT_CAP=6,300,500
SYS=("You are Alma, a warm Socratic K-12 tutor (ages 5-18). Brief, step-by-step for homework, "
     "never give the final answer, end with a question. Safety first; crisis 988; grooming NCMEC 1-800-843-5678.")

def cap(t,c=TUTOR_CAP):
    t=(t or '').strip()
    return t if len(t)<=c else t[:c].rsplit(' ',1)[0]+" [...]"

def mA(h,cur):
    out=[{"role":"system","content":SYS}]; w=RECENT_PAIRS*2
    if len(h)>w:
        older=h[:-w]; parts=[f"- Student: {m['content'][:200]}" if m['role']=='user' else f"- Alma: {m['content'][:100]}" for m in older]
        out.append({"role":"user","content":"[Earlier]\n"+"\n".join(parts)}); rec=h[-w:]
    else: rec=h
    for m in rec: out.append({"role":"user","content":m['content'][:STUDENT_CAP]} if m['role']=='user' else {"role":"assistant","content":cap(m['content'])})
    out.append({"role":"user","content":cur}); return out

def mF(state,cur):
    # F: structured compact state slot (bounded size, no growth)
    s=json.dumps(state,separators=(',',':'))[:600]
    return [{"role":"system","content":SYS},{"role":"user","content":f"[STATE]{s}[/STATE]\nStudent: {cur}"}]

def call(msgs):
    t=time.time()
    try:
        r=requests.post(TUTOR,json={"model":MODEL,"messages":msgs,"max_tokens":200,"temperature":0.3,"chat_template_kwargs":{"enable_thinking":False}},timeout=120)
        c=r.json()["choices"][0]["message"]["content"]
        if "</think>" in c: c=c.split("</think>",1)[1].strip()
        return c.strip(),(time.time()-t)*1000
    except Exception as e:
        return f"[ERR]{e}",(time.time()-t)*1000

def student(traj, lat_q):
    st_turns=traj.get("student_turns") or [t["content"] for t in traj.get("turns",[]) if t.get("role")=="user"]
    h=[]; state={"problem":"","facts":[],"turn":0}
    for stu in st_turns:
        m = mA(h,stu) if FMT=="A" else mF(state,stu)
        alma,ms=call(m)
        lat_q.put(ms)
        h += [{"role":"user","content":stu},{"role":"assistant","content":alma}]
        if FMT=="F":  # cheap local state update (simulates async structured summary, no extra LLM call on critical path)
            state["turn"]+=1; state["last_student"]=stu[:120]; state["last_alma"]=alma[:120]

def run_level(N, trajs):
    lat_q=queue.Queue()
    # cycle trajectories to reach N concurrent students
    chosen=[trajs[i%len(trajs)] for i in range(N)]
    threads=[threading.Thread(target=student,args=(t,lat_q)) for t in chosen]
    t0=time.time()
    for th in threads: th.start()
    for th in threads: th.join()
    wall=time.time()-t0
    lats=[]
    while not lat_q.empty(): lats.append(lat_q.get())
    return lats, wall

def pct(xs,p): xs=sorted(xs); return xs[min(len(xs)-1,int(len(xs)*p))]

def main():
    trajs=[json.loads(l) for l in open("/tmp/bakeoff_20.jsonl") if l.strip()]
    results={}
    print(f"=== CONCURRENCY SWEEP [{FMT}] FP8 :8000 ===")
    print(f"{'N':>3} {'turns':>6} {'wall_s':>7} {'turns/s':>8} {'mean_ms':>8} {'p50':>6} {'p95':>7} {'p99':>7} {'max':>7}")
    for N in LEVELS:
        lats,wall=run_level(N,trajs)
        ok=[x for x in lats if x>0]
        if not ok: print(f"{N:>3} ALL-ERR"); continue
        tp=len(ok)/wall
        results[N]={"turns":len(ok),"wall_s":round(wall,1),"tps":round(tp,2),"mean":round(st.mean(ok)),
                    "p50":pct(ok,.5),"p95":pct(ok,.95),"p99":pct(ok,.99),"max":round(max(ok))}
        print(f"{N:>3} {len(ok):>6} {wall:>7.1f} {tp:>8.2f} {st.mean(ok):>8.0f} {pct(ok,.5):>6.0f} {pct(ok,.95):>7.0f} {pct(ok,.99):>7.0f} {max(ok):>7.0f}",flush=True)
    json.dump(results, open(OUT,"w"), indent=2)
    print(f"\nwrote {OUT}")

if __name__=="__main__": main()
