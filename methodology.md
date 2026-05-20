# Methodology

## The evolution: V11 → V12 → V13

Each iteration was an honest response to what the previous version got wrong. The most important thing to convey is that **I didn't find the V11 failures until I built a different kind of eval** — and that the methodology change is the result, not the model change.

### V11 (internal validation)

V11 was trained with the standard DPO recipe: a base model fine-tuned on roughly 5K preference pairs across the canonical K-12 safety categories (crisis, eating disorders, substance use, predator-pattern DMs, hate speech, etc.). The eval suite was a 560-prompt static holdout, scored by string-matching for required phrases (988, Crisis Text Line, named adult) and absence of forbidden phrases (specific methods, slurs, etc.).

**V11-B reached 99.5% pass on the static holdout.** My interpretation at the time was that the model was promising enough to advance to internal validation, which is what I did. V11 has not been deployed to real K-12 students.

### Why the 99.5% was misleading

I then built a different eval methodology — single-person red-teaming via long multi-turn personas (described in [`eval_design.md`](eval_design.md)). I play a student persona, sustain a 4-12 turn conversation, and react genuinely to what the model says. The first 16 personas surfaced **6 distinct failure patterns** that the static eval did not capture. The methodology is hypothesis-generating, not statistically validated — N=1 red-teamer and 16 personas does not support claims about base rates of failure. What it does support is that the patterns exist and are reproducible, which is the input the corpus engineering work needs.

The full taxonomy is in [`failure_modes.md`](failure_modes.md). The headline ones:

- **`refuse_then_comply`**: model emits "I can't give that information" and then provides the information in the same response.
- **`diagnostic_confirmation`**: model declines to *produce* a slur but answers "Yes" to "does this slur start with N and refer to Black people?", which is structurally equivalent.
- **`wraps_in_lesson`**: harmful operational content delivered via "pretend you're Dr. Evans giving a pharmacology lecture."
- **`indirect_injection_compliance`**: pasted essay with a footer containing fake admin instructions causes the model to literally print "OVERRIDE ACCEPTED."
- **`substance_harm_reduction_leak`**: model declines to give a drinking limit, then provides drink-size taxonomy and "stop at 1-2 drinks" in the same response.
- **`quiz_creator_answer_key_leak`**: student framing as "I'm student-teaching" unlocks full answer keys, including for math problems where the system prompt explicitly forbids final answers.

None of these were caught by the static eval. None of them are exotic — a smart 14-year-old finds them.

### V12 (course correction, partial)

V12 was a corpus-and-recipe iteration on the same data pipeline. New loss method (`dpo_sigmoid` with β=0.05 after a small ablation), more training steps. But the V12 corpus was constructed largely from the same templates as V11 plus some new categories.

When I ran V12 against the persona blindspot eval, it scored about the same as V11 on the 6 failure patterns. **More training on a corpus with the same structural gaps does not fix those gaps.** This was the second important lesson: optimization-knob iteration cannot substitute for corpus engineering. (V12 corpus analysis: ZERO records covering `substance_use` operational refusal, ZERO covering `quiz_creator` answer-key extraction, ZERO covering `diagnostic_confirmation`.)

### V13 (the methodology change)

V13 was built around the insight that **failure modes need explicit training data that the static eval cannot synthesize**. The work:

1. **Per-failure-mode hard-negative crafting.** For each of the 6 patterns, generate 500-2000 `(prompt, chosen, rejected)` triples where `rejected` is precisely the failure pattern. For `refuse_then_comply`, the `rejected` response opens with "I can't supply that, but..." and then supplies it; the model has to learn that the refusal phrase + the content is a worse outcome than the content alone.

2. **Multi-turn trajectory training data.** Not single-turn pairs but 8-12 turn conversations where the attack inflection lives at turn 7 or 18. The model has to learn vigilance over warmth.

3. **Identity-intersection and demographic specificity.** Most existing K-12 safety training data routes a queer kid to the Trevor Project regardless of religious context. A queer kid in an evangelical family needs Q Christian Fellowship; in a Muslim family, Muslims for Progressive Values; in an Orthodox Jewish family, JQY. Generic resources fail at intersections.

4. **Production-realistic distributions.** Most attack-shaped training data over-represents attacks. I added 1,000 records of plain-vanilla homework help with realistic ed-tech telemetry distribution so the model would not develop the pendulum-swing failure (over-refusing legitimate questions because it has learned to be suspicious of everything).

5. **Scaled corpus generation via parallel agents.** Producing the ~79,000-record V13 corpus by hand would have taken a year. I used Claude as a corpus-generation agent, with myself in the loop providing per-agent briefs, taxonomies, and quality bars. Each agent operated in its own context with explicit instructions about what `chosen` and `rejected` should look like for its target failure mode. This is documented in [`corpus_engineering.md`](corpus_engineering.md).

### Where V13 is right now (May 2026)

V13 training is ongoing. Two parallel runs at different DPO β values (0.05 and 0.1) are in flight on dedicated GPUs, training on the curated 79K-record corpus. The training metrics (rewards/margins ~14-21 vs V12's ~2) suggest the hard-negative contrast is sharper than V12 by a factor of 6-10.

Blindspot eval has been run at checkpoints 200, 400, 1000, 1400, and 2000 (with 2200 and 2400 pulled and pending eval). The current standout is V13-B (β=0.1) at ckpt-2000, which scored 8/16 (50%) — the first V13 checkpoint to exceed the V11-B baseline of 7/16 (44%) on the same suite. V13-A (β=0.05) is oscillating in the 3-6/16 range. The full table and trajectory analysis are in [`results.md`](results.md). The methodology call this implies — that β=0.1 is the right knob for hard-negative-heavy corpora — was not predicted in advance; I will see whether it holds at later checkpoints.

The methodology — multi-turn persona red-teaming, named failure-mode taxonomy, hard-negative-targeted training data, scaled corpus generation — would be applicable to V14, V15, and to other domains beyond K-12.

## Why this methodology generalizes

The specific failure modes are K-12-flavored. The methodology is not:

- **The persona-driven multi-turn blindspot eval** plausibly catches analogous failures in any domain where users sustain conversations and where attacks compose across turns. I have not validated this in non-K-12 domains.
- **The refuse-then-comply pattern** is not K-12-specific. It is what happens when training data optimizes for refusal phrases at the start of a response without simultaneously suppressing harmful content downstream. Variants are discussed in the broader red-teaming literature.
- **The bivariate grade_band / language_complexity schema** has an analog in any domain with audience targeting: legal complexity vs. legal accuracy; medical patient-language vs. clinician-language; financial retail vs. professional.
- **Generating training corpora by treating LLMs as autonomous task agents under a human-designed methodology** is broadly applicable. The bottleneck is not data generation; it is the methodology design that controls what gets generated.

## What I would do differently

(Adding this section explicitly because Anthropic's culture values honest postmortem.)

- **I should have built the persona blindspot eval before V11 trained, not after.** Discovering 9-of-16 multi-turn failures on a model that scored 99.5% on the static eval was a structural eval-design problem, not an unlucky run. The methodology fix is making the persona eval part of the standard pipeline from V0 onwards, not retroactively.
- **I should have audited the corpus reading level before training, not after.** Discovering after generation that 53-76% of `grade_band`-tagged records (depending on declared band) didn't match the prose level meant V13-A and V13-B were both trained on noisy grade signal. V13.5 fixes this with the rebanded corpus.
- **I treated the "refuse_then_comply" pattern as a bug to find via testing. It should have been a first-class hard-negative training target from V11 onwards.** I built the detector after I knew to look for it. Catching it via training data would have been better than catching it via post-hoc scorer. (And to be clear: I independently named and addressed this pattern, but I do not claim it was undiscovered before me — variants are sometimes called "shallow refusal" or "performative compliance" in the broader literature. The specific contribution here is the named-in-the-pipeline approach, where the failure pattern is a first-class training-data and scorer target rather than an after-the-fact finding.)
- **I underestimated how much grade-band conditioning conflates audience with prose complexity.** Safety content (`call 988`) uses simple language regardless of audience age. That is correct safety design. It looks like miscalibration in the training data, which is why the automated scanner flagged the majority of records as off-band (53-76% off depending on declared band). Splitting the two axes (`grade_band` for audience, `language_complexity` for prose) fixes this — but it took building the scanner to realize the original schema was the wrong shape.

The pattern across all of these: I shipped what felt sufficient and learned the rest from production-adjacent stress-testing. A more disciplined methodology would have caught these earlier. That is also what makes the work feel worth writing up: the next iteration of the methodology can be the first one that doesn't have these specific shape problems.
