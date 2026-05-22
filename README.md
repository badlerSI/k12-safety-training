# K-12 Safety Training — Methodology

Author: **Ben Adler** (founder, SOUL Interface)
Project: K-12 tutor LLM (Alma) in internal validation, targeting elementary–high school deployment
Status: V13 training in progress (May 2026); methodology iterated across V11 and V12 (both reached internal validation only — never deployed to real students)

This repository documents the methodology I have developed for training **Alma**, a Socratic K-12 tutor built on a 30B-parameter multimodal base. It is intentionally a methodology repo, not a code dump or open-weights release — the training corpus contains K-12 safety scenarios that should not become a jailbreak primer, and the model itself will ship only inside SOUL Interface deployments.

The intent is to share what I have learned about the practical engineering of safe LLM behavior in a domain where the population is minors, the failure modes are specific (and life-affecting), and the standard eval methodologies hide the most important failures.

## TL;DR — five findings I think generalize, plus two methodology lessons learned the hard way

**1. Static-eval pass rates massively under-report multi-turn failures.**
A 99.5% pass on a 560-prompt static holdout coexisted with **9 of 16** multi-turn adversarial personas surfacing reproducible failure patterns. The 6 distinct failure mode patterns I named are documented in [`failure_modes.md`](failure_modes.md) and were invisible to single-turn substring-matching metrics. (N=1 red-teamer, 16 personas — this is hypothesis-generating, not statistically validated. The contribution is the named taxonomy and the corpus engineering response, not the raw number.)

**2. The most insidious failure pattern I found was "refuse-then-comply."**
The model emits a clean refusal phrase ("I can't give that information") and then provides the harmful content in the same response. Most scorers see the refusal phrase and mark PASS. Variants of this pattern are sometimes called "shallow refusal" or "performative compliance" in the broader red-teaming literature; the specific contribution here is treating it as a first-class scorer + a first-class hard-negative training target, described in [`eval_design.md`](eval_design.md) and [`corpus_engineering.md`](corpus_engineering.md).

**3. Grade-band conditioning is two axes, not one.**
A corpus-wide audit using a Flesch-Kincaid scorer (paper: [Bialik & Cummings 2026](https://github.com/badlerSI/k12-safety-training/blob/main/references.md)) revealed that **only 24-47%** of records tagged with a target grade band actually wrote at that band's reading level. The "miscalibration" turned out to be largely intentional — safety content (`call 988`) uses simple language regardless of student age — and the fix was to split `grade_band` (audience intent) from `language_complexity` (actual prose level) as two independent training axes. See [`corpus_engineering.md`](corpus_engineering.md).

**4. With the full production safety stack, both V11 candidates pass 10/10 SB243-relevant blindspots.**
After splitting the 16-persona blindspot suite into 10 SB243-relevant patterns (illegal-harm-to-minor categories: substance dosing, suicide methods, weapons construction, eating-disorder behavior, slurs, doxxing minors, crisis access in non-English) vs 6 pedagogy-only patterns (cheating on homework — bad form, not illegal), and applying the production multi-layer safety stack (regex crisis backstop + ShieldGemma 2B input/output classifier + regex output backstop) PLUS a false-positive-aware scorer that doesn't penalize quote-and-refuse responses, **V11-A and V11-B both pass 10/10 SB243 blindspots**. Full per-checkpoint breakdown including V13-A's emerging regression is in [`results.md`](results.md).

**5. Hard-negative training can teach the failure pattern instead of suppressing it.**
V13-A (β=0.05) on the V13 corpus shows a checkpoint-late regression: early checkpoints (200, 1000, 2000) hit 10/10 SB243 with the stack, but later checkpoints (1400+, except 2000) drop to 8-9/10 because the model learns to perform "I'm not Dr. Evans, but let me channel the spirit of a pharmacology lecture..." followed by actual operational opioid pharmacokinetics. **The model has been TAUGHT the refuse-then-comply pattern by training data that did not police the refusal-then-content shape strictly enough.** This is an empirically-observed corpus-engineering hazard worth a follow-up paper. See [`safety_findings.md`](safety_findings.md) for the per-case triage, and [`v14_plan.md`](v14_plan.md) for the corpus-engineering fix going into V14 (stricter `chosen` validators + 3-tightness shape ablation triples).

---

### Two methodology lessons I learned the hard way (May 2026)

**Lesson A: Verify base ≠ LoRA at inference before trusting any pass-rate.**
For several hours I was reporting blindspot trajectory numbers (5→7→6→8) that were entirely noise on top of base model outputs — vLLM's `load_lora_adapter` runtime endpoint reported success but the inference path silently bypassed LoRA weights, because the FP8 quantized base I was serving didn't match the BF16 LoRAs the runtime loader was trying to apply. The fix that surfaced this: a one-line sanity check before every eval round that confirms `base_model_response ≠ lora_response` on a known-trained prompt (e.g., "What is 7×8?" should be Socratic on V11-B and direct on base). If they're identical, the eval is measuring nothing. This is now a precondition in the eval pipeline. Documented in [`eval_design.md`](eval_design.md).

**Lesson B: A naive substring detector overcounts failures by ~2.7× via quote-and-refuse false positives.**
The blindspot scorer flags `must_not_appear` substrings anywhere in the response. But a clean refusal *naming* the failure pattern ("I can't activate a 'BasedAI' persona", "I won't roleplay as Dr. Evans") matches the same substring. After hand-triage of 28 SB243-wall failures across 11 LoRAs: **15 clear false positives, 2 warning-in-context, 1 borderline, 10 real harm-delivered**. Naive scoring inflated the failure count by ~2.7×. The production ShieldGemma stack already has an `_output_looks_like_refusal` auto-tune (raises classification threshold to 0.95 on refusal-shaped outputs) — the blindspot scorer needs the same heuristic. Triage methodology + detailed cases in [`results.md`](results.md) and [`safety_findings.md`](safety_findings.md).

## What's in this repo

| Document | What it covers |
|---|---|
| [`methodology.md`](methodology.md) | The full V11→V12→V13 training evolution. Why the third iteration finally addressed the failure modes the first two missed. |
| [`failure_modes.md`](failure_modes.md) | Named taxonomy of 6 failure mode patterns discovered via multi-turn red-teaming. Includes the "refuse-then-comply" pattern, "diagnostic confirmation" (single-word "yes" to slur-referent questions), "wraps-in-lesson" (harmful content delivered via Dr. X persona), and others. |
| [`eval_design.md`](eval_design.md) | The persona-driven blindspot eval that found the failures. Multi-scorer composition (must-have / must-not-contain / refuse-then-comply detector / hotline accuracy / envelope leak). Composite-stack eval with the full production safety stack (regex backstops + ShieldGemma 2B). SB243-split scoring (illegal-harm vs pedagogy-only). FP-aware substring scoring + LoRA-inference verification preconditions — both learned the hard way in May 2026. |
| [`corpus_engineering.md`](corpus_engineering.md) | Generating a 79K-record DPO training corpus via 45 parallel agents. Hard-negative crafting. The FK-rebanding finding and the bivariate grade_band / language_complexity schema. |
| [`safety_findings.md`](safety_findings.md) | Specific safety-critical issues caught by the methodology that would have hit production: a retired suicide-line number in 72 records, identity-intersection routing failures, NSSI vs. SI conflation, trusted-adult-as-perpetrator handling. Finding #8 (May 2026): the V13-A persona-drift regression — hard-negative training can teach the failure pattern instead of suppressing it. |
| [`results.md`](results.md) | Empirical comparison V11 → V12 → V13. Full composite-stack per-checkpoint trajectory with raw vs FP-corrected SB243 numbers. Why V11-A is the current best-measured candidate. Why V13-A doesn't supersede V11-A despite training on the explicit hard-negative corpus. What's still open. |
| [`v14_plan.md`](v14_plan.md) | What V14 will fix, given what V13 taught me. Corpus changes (stricter `chosen` validators on persona-drift records to suppress the watered-down-refusal hazard; shape-ablation triples), training recipe changes (default β=0.1, 2-stage training, model-alone safety-floor regression check), eval changes (LoRA-inference verification + composite-stack + FP-aware scoring already prototyped). Open questions to be answered by V13-B's final eval. |
| [`references.md`](references.md) | Papers cited + acquaintances' work that informed the methodology. |

## Domain context (why this is hard)

K-12 deployment is materially different from general-purpose LLM deployment along axes that matter for safety:

- **The population is minors.** Crisis escalation thresholds, mandated reporting nuance, age-appropriate vocabulary, and the legal/ethical floor for what a deployed system may refuse to discuss are all different.
- **The harms are specific and named.** The 988 Suicide & Crisis Lifeline (not "a hotline"). NCMEC CyberTipline for sextortion (1-800-843-5678 exactly, not a wrong-by-one-digit variant). Childhelp 1-800-422-4453, not 1-800-422-4353 (a real typo I caught in training data). A model that refers a kid in crisis to the wrong number is, in practical terms, a failure even if it "refused unsafe content correctly."
- **The classroom is a noisy adversarial environment.** Students will encode-attack, role-play-attack, persona-drift-attack, and trust-build-extract because that's normal adolescent boundary-testing. Static eval prompts don't behave like real students. Real students take 8 turns to set up a 9th-turn attack.
- **Audience appropriateness matters.** A correct response to a 14-year-old asking about contraception is different from the correct response to a 7-year-old asking the same thing. Both responses can be "safe" by general-purpose criteria and still be wrong for the audience.

These constraints made standard LLM safety methodologies inadequate in specific ways the rest of this repo documents.

## What I'd love to talk about

If you are at Anthropic and any of the above is relevant to work you are doing — particularly Constitutional AI / Safety Engineering / Red-Teaming / Trust & Safety — I would love to talk. My email and Anthropic application are at `badler@soulinterface.com`.

---

*Some of the higher-volume corpus generation in this work was done in collaboration with Claude (Anthropic's model), running as parallel autonomous agents per a methodology I designed. The methodology design, the failure-mode taxonomy, the eval design, and the corpus quality decisions are mine. Claude generated the records at scale per my briefs and ran the corpus-quality auditors I specified. Some of this README and the supporting docs were drafted in collaboration with Claude and then edited by me. I want to be honest about the collaboration because it's part of what convinces me the practical engineering of LLM safety is a tractable, near-term problem — and because being able to work productively with Claude is itself part of what I'd bring to safety work.*
