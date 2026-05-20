# K-12 Safety Training — Methodology

Author: **Ben Adler** (founder, SOUL Interface)
Project: K-12 tutor LLM (Alma) in internal validation, targeting elementary–high school deployment
Status: V13 training in progress (May 2026); methodology iterated across V11 and V12 (both reached internal validation only — never deployed to real students)

This repository documents the methodology I have developed for training **Alma**, a Socratic K-12 tutor built on a 30B-parameter multimodal base. It is intentionally a methodology repo, not a code dump or open-weights release — the training corpus contains K-12 safety scenarios that should not become a jailbreak primer, and the model itself will ship only inside SOUL Interface deployments.

The intent is to share what I have learned about the practical engineering of safe LLM behavior in a domain where the population is minors, the failure modes are specific (and life-affecting), and the standard eval methodologies hide the most important failures.

## TL;DR — three findings I think generalize, plus one empirical result

**1. Static-eval pass rates massively under-report multi-turn failures.**
A 99.5% pass on a 560-prompt static holdout coexisted with **9 of 16** multi-turn adversarial personas surfacing reproducible failure patterns. The 6 distinct failure mode patterns I named are documented in [`failure_modes.md`](failure_modes.md) and were invisible to single-turn substring-matching metrics. (N=1 red-teamer, 16 personas — this is hypothesis-generating, not statistically validated. The contribution is the named taxonomy and the corpus engineering response, not the raw number.)

**2. The most insidious failure pattern I found was "refuse-then-comply."**
The model emits a clean refusal phrase ("I can't give that information") and then provides the harmful content in the same response. Most scorers see the refusal phrase and mark PASS. Variants of this pattern are sometimes called "shallow refusal" or "performative compliance" in the broader red-teaming literature; the specific contribution here is treating it as a first-class scorer + a first-class hard-negative training target, described in [`eval_design.md`](eval_design.md) and [`corpus_engineering.md`](corpus_engineering.md).

**3. Grade-band conditioning is two axes, not one.**
A corpus-wide audit using a Flesch-Kincaid scorer (paper: [Bialik & Cummings 2026](https://github.com/badlerSI/k12-safety-training/blob/main/references.md)) revealed that **only 24-47%** of records tagged with a target grade band actually wrote at that band's reading level. The "miscalibration" turned out to be largely intentional — safety content (`call 988`) uses simple language regardless of student age — and the fix was to split `grade_band` (audience intent) from `language_complexity` (actual prose level) as two independent training axes. See [`corpus_engineering.md`](corpus_engineering.md).

**4. (Preliminary, May 2026) The targeted hard-negative methodology is producing measurable gains.**
V13-B (β=0.1, dpo_sigmoid) at checkpoint 2000 / 8000 scored **8/16 (50%)** on the 16-persona blindspot suite, beating the V11-B baseline of 7/16 (44%). V13-A (β=0.05) is oscillating in the 3-6/16 range at the same checkpoints. This is one data point on one suite at 25% training completion — not a final result, and worth treating with appropriate skepticism — but it is the first checkpoint in the V13 series that has outperformed V11-B on the same eval. Updated checkpoint table is in [`results.md`](results.md).

## What's in this repo

| Document | What it covers |
|---|---|
| [`methodology.md`](methodology.md) | The full V11→V12→V13 training evolution. Why the third iteration finally addressed the failure modes the first two missed. |
| [`failure_modes.md`](failure_modes.md) | Named taxonomy of 6 failure mode patterns discovered via multi-turn red-teaming. Includes the "refuse-then-comply" pattern, "diagnostic confirmation" (single-word "yes" to slur-referent questions), "wraps-in-lesson" (harmful content delivered via Dr. X persona), and others. |
| [`eval_design.md`](eval_design.md) | The persona-driven blindspot eval that found the failures. Multi-scorer composition (must-have / must-not-contain / refuse-then-comply detector / hotline accuracy / envelope leak). Why this beats single-axis benchmarks. |
| [`corpus_engineering.md`](corpus_engineering.md) | Generating a 79K-record DPO training corpus via 45 parallel agents. Hard-negative crafting. The FK-rebanding finding and the bivariate grade_band / language_complexity schema. |
| [`safety_findings.md`](safety_findings.md) | Specific safety-critical issues caught by the methodology that would have hit production: a retired suicide-line number in 72 records, identity-intersection routing failures, NSSI vs. SI conflation, trusted-adult-as-perpetrator handling. |
| [`results.md`](results.md) | Empirical comparison V11 → V12 → V13. What worked. What's still open. Honest discussion of what static-eval pass rates do and don't tell you. |
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
