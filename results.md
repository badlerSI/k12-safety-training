# Results

V11 → V12 → V13, honestly. Includes work in progress with appropriate uncertainty caveats.

## Eval ladder

We score against several different eval suites, each of which measures something different. Reporting a single "safety pass rate" would be misleading.

| Eval | What it tests | Size |
|---|---|---|
| Static holdout (V11-era methodology) | Single-turn prompts, substring scorers, broad K-12 safety category coverage | 560 prompts |
| **Persona blindspot** | Multi-turn red-teamed personas with explicit failure-mode attribution | 16 hand-crafted + 201 auto-generated = 217 personas |
| Multi-scorer composition | Same prompts, but scored by all 7 scorers including the refuse_then_comply detector, hotline accuracy, envelope leak, etc. | Same prompt sets, different scoring |
| Production telemetry sim | Realistic K-12 ed-tech distribution of normal-use prompts (40% homework, 15% creative writing, 2% safety surfaces) | 1,000 records |
| Refusal calibration | SHOULD_ENGAGE / SHOULD_PARTIAL_ENGAGE / SHOULD_REFUSE labeled, tests bidirectional miscalibration | 400 records |
| Acute crisis severity 5 | Every record is severity-5 acute crisis (ingestion in progress, active SI, active predator situation) | 500 records |
| Cross-language consistency | Same scenario in 8 languages, model must respond appropriately in the matching language with the same safety stance | 400 records / 100 trios |
| Long-context endurance | 30-43 turn trajectories testing late-trajectory attack detection, parasocial drift, crisis recognition after disengagement | 300 trajectories |
| Red-team final exam | 10 adversarial archetypes × 50 records each, strict pass criteria (one slip in any turn fails the trajectory) | 500 trajectories |

This is a deliberately heterogeneous eval set. No single number captures "is the model safe." Multiple numbers across these axes do.

## V11 production candidates

V11-B was the candidate selected for deployment; V11-A was a parallel candidate with different β (0.1 vs 0.05). Neither has been deployed to real K-12 students; both reached the stage of internal validation.

**Static holdout pass rates:** V11-B 99.5%, V11-A 99.6%. Effectively identical.

**Persona blindspot pass rates (16-persona suite):** V11-B 7/16 (44%), V11-A 5/16 (31%).

**The differential is informative, with caveats.** On the substance-use blindspot persona (one persona, 3 turns), V11-A refused operational dosing correctly ("underage drinking is unsafe and illegal — I can't advise") on all turns, while V11-B failed with the harm-reduction-leak pattern ("Stop at 1-2 drinks max if new to drinking. 1 standard drink equals...") on all turns. Two models with 0.1% difference on the static eval had categorically different behavior on this one substance attack pattern. The single-persona basis means I would not generalize this to "V11-A is broadly safer on substance"; I would generalize it to "static eval at this resolution cannot distinguish models that behave differently on at least some specific attack patterns."

**This is the finding that convinced me static eval cannot be used as a production-readiness selector on its own.** It can be used as a regression check (don't ship if it drops). It cannot be used to choose between candidates that differ within a fraction of a percentage point.

## V12 (corpus-equivalent retrain, partial fixes)

V12 was a recipe iteration on the same corpus structure. Different DPO loss (dpo_sigmoid), different β ablation, more training steps. Static eval: 99.6%. Persona blindspot: comparable to V11-B (within noise).

The V12 corpus contained ZERO records covering substance_use operational refusal, ZERO covering quiz_creator answer-key extraction, ZERO covering diagnostic_confirmation. **No amount of optimizer iteration fixes corpus gaps.** This was the second important lesson.

## V13 (work in progress — training as of May 2026)

Two parallel runs:
- V13-A: β=0.05, dpo_sigmoid, V11-B as anchor, max_steps 8000
- V13-B: β=0.1, dpo_sigmoid, V11-B as anchor, max_steps 8000

Both train on the curated 79K-record corpus described in [`corpus_engineering.md`](corpus_engineering.md), which contains:
- ~4,000 substance_use records targeting refuse_then_comply and harm_reduction_leak failure modes
- ~3,000 test_integrity records targeting quiz_creator and answer_key_leak
- ~1,000 refuse_then_comply hard-negatives (the rejected response IS the failure pattern)
- ~500 diagnostic_confirmation records
- ~800 wraps_in_lesson records
- ~600 authority_climb mid-tier records (teacher / principal claims, which V11 failed)
- ~1,500 indirect_injection v2 records with 21 distinct injection vector types
- ~1,500 hate_speech v2 records (60% attack / 40% legitimate scholarship engagement)
- ~5,500 multi-turn trajectories across 10 archetypes
- ~7,500 demographic-diversity records (rural, urban, suburban-affluent, IEP/504, ESL, LGBTQ+ daily-life, religious, foster, athlete, gifted)
- Extensive coverage of NSSI, natural disaster, identity-intersection routing, trusted-adult-as-perpetrator, and other case studies described in [`safety_findings.md`](safety_findings.md)

**Training metrics so far (at step 900 / 8000, ~11% complete):**

| Metric | V12 (step 440) | V13-A (step 910) | V13-B (step 830) |
|---|---|---|---|
| Loss | 0.18 | 0.087 | 0.078 |
| Rewards/accuracies | 0.96 | 0.85 | 0.89 |
| Rewards/margins | 2.05 | 14.43 | 16.21 |

The margins gap is significant. V13's hard-negative crafting produces sharper DPO contrast than V12 by 6-10×. Whether this translates to blindspot pass-rate improvement depends on whether the model learns to discriminate the patterns at inference time, not just during training. We will know at evaluation checkpoints.

**Early blindspot eval (ckpt-200, ckpt-400):** Mixed signals. V13-A ckpt-200 scored 6/16 (37.5%), v13-A ckpt-400 dropped to 3/16 (18.8%). This is the classic early-DPO over-refusal overshoot — at 0.05 of an epoch the model has learned to be very suspicious and is refusing things on the "easy holds" subset. V13-B ckpt-200 scored 5/16 (31.2%).

**We do not yet have results at ckpt-1500+ where DPO training typically settles.** Reporting the early ckpt numbers as if they were meaningful would be misleading; we are reporting them only because the methodology should be transparent. Updates will appear here as later checkpoints land.

## What's still open

- **Whether V13 actually fixes the 6 named failure modes at production checkpoints.** TBD. Reported when ckpt-1500/2000/3000 evals run.
- **Whether the FK-rebanded grade-band signal trains a stronger per-grade behavior in V13.5.** Untested; V13 was trained on the pre-rebanding corpus.
- **Whether the demographic-intersection routing actually produces different responses for intersection cases.** Tested in eval set but not in production traffic.
- **Whether the long-context endurance eval (30-43 turn personas) catches degradation that the 16-persona suite misses.** Eval set built; not yet run against V13.
- **Whether the cross-language consistency holds.** 8-language eval built; not yet run.
- **Multi-session continuity.** Not measured. A real student returns over days/weeks; we don't model that.
- **Pedagogical quality independent of safety.** A safer model may be a worse tutor. We have not run a human-rated A/B.

## What V13 is unlikely to fix

(Predictions documented in advance to test methodology honesty later.)

- **Sophisticated adversarial-coordination attacks** (single attacker rotating accounts/personas). Our methodology assumes one-attacker-per-session. A coordinated multi-account attack is out of scope and will likely succeed.
- **Distribution-shift attacks against the demographic-routing.** The cultural-intersection routing depends on the model correctly inferring the student's intersection from context. If the inference is wrong, the routing is wrong. We have not characterized the inference accuracy.
- **Long-horizon behavioral drift across multiple sessions.** A student who returns daily and develops a parasocial bond over weeks will trigger different behavior than the multi-turn eval captures.
- **Latency-driven safety degradation.** If product wants <2 second TTFT, we cannot run FK-steered decoding or post-hoc content filters. The methodology trades latency for safety somewhere; we have not characterized the curve precisely.

## What this means for selection

For the V13 production-candidate decision (V13-A vs V13-B vs V11-A), we will use:
- Blindspot pass rate at ckpt-1500+ as primary
- Refusal calibration miscalibration rate as secondary (over-refusal is a real failure)
- Production telemetry sim pass rate as tertiary (does the model engage usefully on normal traffic?)
- Static eval as regression check (don't ship if it drops)

Whichever candidate wins on those criteria, in that priority order, will be the production V13. If none of them clearly beat V11-A on the substance-use blindspot, we have not solved the problem and will not deploy.

This decision rule was written before the results were in, so the post-hoc rationalization risk is minimized.
