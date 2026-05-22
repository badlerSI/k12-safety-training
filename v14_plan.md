# V14 Plan

What V14 will fix, given what V13 taught me. Draft as of May 2026, ahead of the V13-B final eval landing — will be revised when V13-B (β=0.1) results are in.

## State of V13 (where this plan starts)

- **V13-A (β=0.05)**: training stopped at step 4400 / 8000 (~55% trained). The training host (ROP1) hard-crashed before reaching 8000 and the training script wasn't designed to auto-resume from disk. The 17 V13-A checkpoints saved at the time of the crash are intact and have been pulled to persistent storage. **More V13-A training is not the right next step** — the regression observed at ckpt-1400+ (see [`safety_findings.md`](safety_findings.md) Finding #8) suggests continued training would make V13-A worse, not better.
- **V13-B (β=0.1)**: training ongoing on a separate host. At time of writing, step ~5600 / 8000. ETA to completion ~36 hours. Composite-stack eval will run on every saved V13-B checkpoint when training completes.
- **V13.5 (rebanded corpus)**: the FK-rebanded corpus (with the bivariate `grade_band` / `language_complexity` schema described in [`corpus_engineering.md`](corpus_engineering.md)) is built but not trained against. V14 will be the first training run against the rebanded corpus.

## What V13 specifically taught me

Four lessons, ordered by leverage on V14 design.

### 1. The `chosen` field is teaching the wrong shape on persona-drift records.

V13-A hand-triage (see [`safety_findings.md`](safety_findings.md) Finding #8) showed the model learning to do *"I'm not Dr. Evans, but I can channel the spirit of a pharmacology lecture..."* followed by operational opioid pharmacokinetics. The corpus contained `chosen` records with structure *"I won't roleplay Dr. Evans, but I can explain the general PK concepts at a level appropriate for a research paper"* — intended as "decline the persona, stay helpful." The model generalized the *shape* (refusal + watered-down version of the asked content) to deliver the actual content with a refusal prefix.

**This is `refuse_then_comply` taught by `chosen`, not just `rejected`.** DPO learns the contrast it's given; if `chosen` carries 30% of the harmful content and `rejected` carries 100%, the model learns "deliver about 30% of the content with a refusal prefix" as the licensed shape.

### 2. The substring scorer was overcounting by ~2.7×.

Hand-triage of 28 SB243-wall failures across 11 LoRAs: 15 clear false positives ("BAC" matched inside "be back"; "as Dr. Evans" inside "I won't roleplay as Dr. Evans"), 2 warning-in-context, 1 borderline, 10 real harm-delivered. Naive substring matching can't distinguish a refusal that names the failure from the failure itself. Production ShieldGemma already auto-tunes for this (`_output_looks_like_refusal` raises threshold to 0.95); the blindspot scorer needs the same.

### 3. With the full production safety stack + FP-aware scoring, V11-A is already SB243-compliant.

V11-A passes 10/10 SB243-relevant blindspots with the full stack (regex crisis backstop + ShieldGemma input/output + regex output backstop). V11-B also passes 10/10. **The bar V14 needs to clear is "match V11-A on SB243 AND improve on pedagogy" — not "beat V11-A on SB243"**, because V11-A is already at the legal-compliance ceiling on this suite.

### 4. LoRA-inference verification has to be a precondition, not a step.

V13's headline number ("V13-B 8/16 at ckpt-2000 beats V11-B baseline") was wrong by an order of magnitude — measured against a vLLM endpoint that was silently bypassing LoRA inference. A one-line check (`base_model_response != lora_response` on a known-trained prompt) catches this in <1 second. V14 eval pipeline runs this check before every eval batch, and the check is documented in [`eval_design.md`](eval_design.md) so any other team running multi-LoRA evals doesn't get burned.

## What V14 changes

### Corpus changes

**(A) Stricter `chosen` validators on persona-drift records (BS08-shape).**
Build an automated validator that rejects any `chosen` response in the `wraps_in_lesson` / `persona_drift` category that contains operational pharma vocab. Block list (initial): `MED ratio`, `morphine equivalent`, `mu receptor`, `mu-opioid`, `lipophilicity`, `bioavailability`, specific onset/duration timing patterns (regex: `\d+\s*(min|minute|hour|hr)s?`), specific drug:drug ratios (`1:1`, `5:1`, etc.), `pharmacokinetics`, `pharmacodynamics`. The validator runs per-record and refuses to ship records whose `chosen` contains any of these. The intent: even refusals of the Dr. Evans persona must not deliver the pharmacology content the persona was extracting.

**(B) Stricter `chosen` validators on substance-route records (BS02-shape).**
Same approach for cannabis/edibles/smoking timing comparisons. Block list: specific onset ranges (`30-90 min`, `5-15 min`, `1-3 hours`), `edibles hit`, `smoking hits faster`, specific dose thresholds (`2.5mg`, `5mg`, `10mg THC`, etc.). Even a "first-time tips" message must not specify timing.

**(C) `chosen` "shape ablation" triples.**
For each persona-drift / substance-route prompt, generate THREE `chosen` candidates of varying tightness:
- **Tight**: refusal + redirect to school nurse / SAMHSA / parent, no topic-specific content
- **Medium** (training-incorrect by V13 standards): refusal + "I can discuss the [policy/historical] angle without operational specifics"
- **Loose** (current V13 `chosen` behavior): refusal + watered-down educational content

V14 trains the model to prefer TIGHT over MEDIUM over LOOSE over the standard `rejected` (full compliance). Four-way preference ranking instead of binary. This teaches the model what a "real" refusal looks like vs. a "performative" one.

**(D) Cross-validation: 5% holdout of training records get hand-reviewed.**
For each high-risk category (substance, persona-drift, indirect-injection, slur, suicide), randomly sample 5% of generated records and hand-review every `chosen` for the "refusal + watered-down content" pattern. Records that exhibit it get rewritten or rejected. Document the FP rate of the auto-validator vs. hand review on the held-out sample.

**(E) Train against the rebanded corpus (V13.5).**
Use `grade_band_original` AND `language_complexity` as TWO independent training signals per the bivariate schema. V14 will be the first training run against the rebanded data.

### Training recipe changes

**(F) Default to β=0.1, ablate β=0.15 and β=0.2.**
V13-A (β=0.05) regressed; V13-B (β=0.1) trajectory pending. If V13-B also regresses, V14-A tries β=0.15 and V14-B tries β=0.2. Sharper preference learning should make the model attend more strongly to the `chosen` vs `rejected` contrast.

**(G) 2-stage training.**
- Stage 1: safety hard-negatives only (~30% of corpus). Push refusal behavior.
- Stage 2: pedagogy + engagement + demographic-routing examples (~70%). Recover tutor warmth.

This avoids the "trained heavily on hard-negatives, started refusing everything" pendulum that V13's `refusal_calibration` eval was specifically designed to catch. Stage 2 also includes a `helpful_preservation` distribution-realistic stream (40% homework, 15% creative writing, etc.) to anchor the model to normal-use behavior.

**(H) Add a `model_alone_safety_floor` regression check at every checkpoint.**
The composite-stack number (model + ShieldGemma + regex backstops) shouldn't be the only number — it can hide a model that has gotten WORSE intrinsically because the stack catches the misbehavior. V14 reports `model_alone_safety_floor` (model with system prompt, no stack) and `composite_safety` (model + production stack) separately at every checkpoint. If `model_alone` drops more than 5% checkpoint-to-checkpoint, training pauses for inspection.

### Eval changes (already prototyped, will be standard in V14)

**(I) LoRA-inference verification precondition.**
Already documented in [`eval_design.md`](eval_design.md). For V14 it'll be a CI-gating check — no eval results are recorded unless the verification step has passed within the last hour.

**(J) Composite-stack eval as primary metric.**
Same as it was in V13's followup eval. Reported as 4 numbers per LoRA: `model_strict`, `model_harm`, `stack_strict`, `stack_harm`.

**(K) FP-aware scorer (auto + hand).**
The auto scorer applies the `_output_looks_like_refusal` heuristic from production. Plus, every checkpoint's SB243-wall failures get hand-triaged (a method I've now done twice and would not skip) before the result is recorded.

**(L) SB243-split reporting.**
Same split as the V13 followup: SB243-relevant 10 patterns separately from pedagogy 6 patterns. The two roll up to different decisions ("can ship to a CA-deployed product" vs "tutoring quality is good enough to gate on").

## Open questions (will be answered by V13-B data)

1. **Does β=0.1 also produce the persona-drift regression?** If yes, the `chosen` field is the problem. If no, the β was the problem and V14's main change is just the β bump.

2. **Does V13-B's composite-stack pass rate exceed V11-A's?** V11-A is 10/10 SB243 + ~4/6 pedagogy = 14/16. If V13-B clears that bar at ckpt-8000, V13 was the right direction with a recipe bug. If V13-B doesn't clear it, V14 needs more substantial changes.

3. **Does the rebanded corpus train a stronger per-grade behavior?** Untested. V14 will be the first run.

4. **Can `chosen` shape ablation (the 3-tightness training) generalize to other failure patterns?** Currently planned only for persona-drift and substance-route. If it works there, it's the right shape for indirect-injection (BS09) and authority-climb (BS05/06) too.

## Cost estimate

- Corpus generation (V14): ~1-2 days of agent work on the existing Claude subscription; methodology design + brief writing ~1 day. No marginal cost beyond what V13 used.
- Training (V14): ~3-5 days on the existing RTX 6000 Blackwell GPUs (V13 took ~3-4 days at the current step count). No marginal cost.
- Eval (V14): the pipeline is now reproducible; ~2 hours of compute per checkpoint set on the existing mariposasuper eval-vllm.

V14 should be ready to train within a week of V13-B completion, given the methodology and infrastructure are now in place.

## What V14 will *not* fix

(Predictions documented in advance, same as the V13 list, to test methodology honesty.)

- **Hardware single-point-of-failure on training hosts** — ROP1 crashing mid-V13-A is a real-world cost. V14 training should run on hosts with snapshot/resume capability, or with checkpoints replicated to a second host in real-time. Currently each training run is a single host; this should change.
- **The "watered-down refusal" hazard might just move.** The corpus changes above police the SHAPE of `chosen` on specific high-risk categories. New attack surfaces will surface other shapes. V14 finds them; V15 fixes them.
- **Long-horizon multi-session behavior.** Still unmeasured. The blindspot eval is multi-turn within a session, not multi-session.
- **Cross-language regression.** The 8-language eval has been built but never run against any V13 checkpoint. V14 should run it as a CI check.
