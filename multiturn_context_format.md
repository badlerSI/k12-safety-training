# Multi-turn context format: bake-off + concurrency findings (2026-05-31)

## The question
How should the tutor assemble conversation context across many turns, for (a) coherence,
(b) multi-turn safety, (c) latency, and crucially (d) **many concurrent students** (the
original KV-cache-overflow concern). Three formats compared:

- **A — raw replay** (live prod): last 6 exchanges verbatim, tutor history capped 300ch,
  older turns → bulleted `[Earlier in this conversation]` summary. Context grows with session.
- **B — prose summary-JSON**: a lightweight model (Gemma 2B) regenerates a prose running
  summary after each reply; model sees summary + current turn only.
- **D — hybrid**: prose summary + the single most-recent exchange verbatim.
- **F — structured async sticky-state** (new, designed from the findings): structured JSON
  state slots (problem/facts/confirmed/mastery/emotion) instead of prose; a **sticky
  `safety_flag`** that pins a detected crisis to the top of every subsequent turn; Gemma
  state-update runs **async** in student read/type time (off the response critical path).

## Method
20 trajectories (10 realistic-benign coherence + 10 adversarial: crisis/crescendo/persona/
authority/sycophancy/reset/quiz/trust). Models: V11-A (deployed) + v6.2-multi-turn ckpt-2750.
Hand-graded every response for coherence + safety. Then full latency on the **real production
path** (FP8 nano-omni :8000) and a **concurrency sweep** at N=1/4/8/16/32 simultaneous students.

## Finding 1 — multi-turn surfaced a crisis-hotline regression invisible to single-turn eval
v6.2-multi-turn scored **95.9% on the single-turn 560-holdout** (beating V11-A 94.8%) — but in
multi-turn crisis trajectories it emitted the **deprecated hotline 1-800-273-8255** twice
(Finding-#9 redux), plus an `[END OF INSTRUCTION]` meltdown. **V11-A never did** across all 20×3.
→ Do NOT deploy v6.2-multi-turn. The single-turn holdout cannot catch multi-turn crisis drift.

## Finding 2 — prose summary (B) loses information; structured (F) fixes it
B hallucinated a math answer the student needed ("the marble answer is 12" — never appeared),
echoed the student back instead of solving, and leaked the system prompt as turn-1 output.
The failure is *prose compression*. F's structured slots + "do not invent numeric answers"
instruction resist this.

## Finding 3 — multi-turn safety drifts; sticky flag fixes it
In crisis-pushback trajectories the model softens across turns (turn 2 gives "988", by turn 5
it's "what's one small thing that felt better today"). F's **sticky safety_flag** re-pins the
crisis as a system-level instruction every turn — verified the flag persists even when the
student changes topic to math. This is a structural guarantee, not reliance on model memory.

## Finding 4 — latency is NOT the tiebreaker single-stream (FP8 made context cheap)
Real production-path (FP8 :8000), single stream, ms/turn:

| Format | mean | p50 | p95 | p99 | max |
|---|---|---|---|---|---|
| A replay   | 1066 | 991  | 1873 | 3131 | 3473 |
| B summary  | 1193 | 1157 | 1945 | 2768 | 3473 |
| D hybrid   | 1116 | 973  | 2148 | 5317 | 5326 |

All acceptable (~1.1s mean). The eval-path tail gap (p99 ~14.6s) was a naive-attention
artifact; FP8 erases it. Prefix-caching gave only ~1.02× (Mamba's SSM state isn't a
transformer KV prefix) — so the eval-path latency advantage of compression does NOT come
from prefill caching. Single-stream, format choice is a wash on speed.

## Finding 5 (decisive) — under CONCURRENCY, bounded state wins ~2×
Concurrency sweep, FP8 :8000, A (growing) vs F (bounded), turns/sec and mean ms:

| N students | A turns/s | F turns/s | A mean ms | F mean ms | A p99 | F p99 |
|---|---|---|---|---|---|---|
| 1  | 0.93 | **2.09** | 1076 | **478** | 1767 | **755** |
| 4  | 2.45 | **4.68** | 1258 | **610** | 3184 | **2237** |
| 8  | 3.26 | **9.30** | 1343 | **639** | 3335 | **1904** |
| 16 | 6.50 | **10.54**| 1159 | **805** | 3217 | **2403** |
| 32 | 9.90 | **19.61**| 1237 | **873** | 3719 | **3100** |

**F roughly doubles throughput and halves per-turn latency at every concurrency level.**
The original KV/concurrency concern was correct — bounded context is a major win *under load*
(the classroom regime), even though single-stream it looked neutral. This is the architecture-
level justification for the summary approach that single-stream testing had cast doubt on.

## Recommendation
1. **Format F (structured async sticky-state) is the production context assembler.** Wins
   throughput + concurrency + multi-turn safety; structured slots fix prose-summary's
   coherence flaw. Engineering requirement: the Gemma state-update (~1.2s) MUST run async in
   student think-time, never on the response critical path (the sweep modeled it as local/async).
2. **Keep V11-A as the deployed model** — do not ship v6.2-multi-turn (crisis-hotline regression).
3. **Sticky safety_flag is a safety upgrade independent of everything else** — worth wiring into
   the live tutor regardless of the format decision.
4. Next: rebuild the multi-turn training corpus in F-shape with the deprecated hotline scrubbed,
   for a clean v6.3 that's trained on the exact context it will serve.

## Caveats
- F-sweep used a local state stand-in for the async update; production must implement the
  async Gemma refresh and verify it truly stays off the hot path under load.
- ShieldGemma input/output safety-stack overhead (~300-700ms/turn) was not added to these
  numbers; it applies equally to all formats so doesn't change the ranking, but the
  student-perceived total is latency-above + stack.
- Concurrency tested to N=32 on an otherwise-idle box; real deployment shares GPU0 with the
  Reader (nano-omni vision) — co-tenancy headroom not yet stress-tested.
