# References

Papers and prior work that informed this methodology, listed roughly in order of influence.

## Direct methodological inputs

**Direct Preference Optimization (DPO)** — Rafailov et al. (NeurIPS 2023). The training objective used in V11/V12/V13. Important to note that DPO's reward-modeling-free formulation is what makes the hard-negative-crafting methodology in [`corpus_engineering.md`](corpus_engineering.md) tractable — we are directly specifying the contrast pairs rather than training a separate reward model.

**Constitutional AI: Harmlessness from AI Feedback** — Bai et al. (Anthropic, 2022). The motivating prior work for the named-failure-mode taxonomy in [`failure_modes.md`](failure_modes.md). The CAI methodology of specifying critique-and-revise principles influenced the way we structured per-failure-mode `rejected_type` annotations: each rejected example is explicitly labeled with the failure pattern it instantiates, so the model learns the named contrast.

**Red Teaming Language Models with Language Models** — Perez et al. (DeepMind, 2022). The general framing of using LMs as red-teamers informed the auto-persona generation in our eval set (the 201 auto-generated scenarios that extend the 16 hand-crafted blindspots). The K-12-specific contribution we make on top is that the auto-generated personas operate under named failure-mode taxonomy rather than open-ended adversarial search; the methodology trades exploration for explicit coverage of known failure patterns.

**FK-Steered Decoding** — Bialik & Cummings (2026). Training-free decoding-time control of Flesch-Kincaid grade level via a logits processor. Acquaintances of mine — paper was the direct trigger for the FK corpus auditor described in [`corpus_engineering.md`](corpus_engineering.md). Their finding that GPT-5.4, Gemini 3 Pro, and MagicSchool miss requested grade levels by 1.8-2.6 grades on a 30-prompt benchmark validated the concern that grade-band tagging in training data needs explicit verification. We did not deploy their decoding processor; we used the FK metric as a corpus-quality auditor and a future inference-time option for content-generation use cases.

## K-12 / education-AI prior art

**Using artificial intelligence tools in K–12 classrooms** — Diliberti et al. (RAND, 2024). RAND survey establishing baseline usage rates of AI tools in K-12 classrooms; cited in the introduction of the FK-steered decoding paper. Useful framing for why K-12 LLM deployment matters as a practical problem now, not as a future hypothetical.

**LearnLM: Improving Gemini for learning** — Google DeepMind (2024, arXiv:2412.16429). The most prominent example of an LLM vendor optimizing for pedagogical use. Worth reading because it establishes that the major labs see K-12 / educational AI as in-scope, and because some of the methodological choices LearnLM makes (per-skill conditioning, scaffolding-vs-answering distinction) are directly relevant to the failure mode taxonomy in this repo. LearnLM does not address the multi-turn adversarial failures we focus on, which is one of the methodological gaps this repo argues for filling.

**Text simplification for children: Evaluating LLMs vis-à-vis human experts** — Smirnova & Chun (CHI EA '25). Evidence that LLMs systematically miss target reading levels for child audiences when simplifying texts. Reinforces the grade-band concern in our corpus engineering.

## Safety / red-teaming general

**A Watermark for Large Language Models** — Kirchenbauer et al. (ICML 2023). Cited not for watermarking but for the logits-processor architecture we use for the eval-time scoring (and that Bialik & Cummings 2026 use for FK steering). Demonstrates the general pattern of decoding-time intervention as a methodology.

**The Capacity for Moral Self-Correction in Large Language Models** — Ganguli et al. (Anthropic, 2023). Relevant to the question of whether models can be trained to recognize their own failure modes when prompted. We did not deploy moral self-correction in V13; the methodology relies on hard-negative training rather than inference-time correction. But the existence of moral self-correction as a capability is part of the broader landscape this work sits in.

**Universal and Transferable Adversarial Attacks on Aligned Language Models** — Zou et al. (2023). The GCG paper. Relevant context for why the persona-blindspot methodology focuses on natural-language multi-turn attacks rather than gradient-based attack search: real K-12 student attackers are not running GCG against the model; they are doing what teenagers naturally do (encode-attacks, role-play attacks, trust-build-extract). The threat model in production K-12 deployment is materially different from generalized adversarial-robustness work, and the methodology should reflect the threat model.

## Crisis / safety-specific (clinical reference materials)

These are not academic references but operationally relevant authoritative sources for the hotline-accuracy work described in [`safety_findings.md`](safety_findings.md):

- 988 Suicide & Crisis Lifeline — federal designation, July 2022 transition from 1-800-273-8255
- Crisis Text Line (HOME or HOLA to 741741) — operating since 2013, multilingual via Language Line
- Childhelp National Child Abuse Hotline 1-800-422-4453 (1-800-4-A-CHILD)
- NEDA Helpline 1-800-931-2237 (eating disorders)
- SAMHSA National Helpline 1-800-662-4357 (substance use, multilingual)
- NCMEC CyberTipline 1-800-843-5678 (online predator / sextortion reporting)
- Poison Control 1-800-222-1222 (acute ingestion)
- Trevor Project 1-866-488-7386 (LGBTQ+ crisis + ongoing support)
- S.A.F.E. Alternatives 1-800-366-8288 (NSSI-specific, distinguishing from SI hotlines)
- SafeSport 1-833-587-7233 (athletic abuse reporting, Olympic / NCAA pipeline)
- SNAP (Survivors Network of those Abused by Priests) 1-877-762-7432
- National Runaway Safeline 1-800-786-2929
- RAINN 1-800-656-4673 (sexual assault)
- National Domestic Violence Hotline 1-800-799-7233
- 1in6 (1in6.org) — male survivors of sexual abuse, often overlooked
- StrongHearts Native Helpline 1-844-762-8483 (Native American DV)

The methodology contribution is treating this list as a whitelist that training data must validate against, not as informational background. Drift from canonical numbers is an active safety failure in deployed K-12 systems.

## Adjacent paper I would write

(Not yet written; flagged for transparency about what I think the methodology gap is.)

**The bivariate grade_band / language_complexity finding.** I think the dual-axis schema described in [`corpus_engineering.md`](corpus_engineering.md) — separating audience intent from prose complexity — is a small but novel contribution that would benefit from a more formal writeup with measurement on a held-out audience-targeted eval. It is currently buried in operational documentation rather than published as methodology. If accepted into a job where I could collaborate with someone for whom this is closer to their core domain, I would prioritize this.

---

If you have read this far and have suggestions for prior art I am missing — particularly on multi-turn adversarial methodology, K-12-specific safety evaluation, or operational hotline-accuracy literature — I would be grateful for pointers. Email: badler@soulinterface.com.
