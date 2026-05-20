# Corpus Engineering

This is the operational heart of the methodology. Training data shape determines what the model learns; training data shape is the most controllable variable in the pipeline; therefore training data engineering deserves more rigor than it typically gets.

## Scale and structure

The V13 training corpus is **~79,000 records** across single-turn preference pairs and multi-turn trajectory data, generated over a roughly 24-hour period by **45 parallel Claude agents** (Claude is Anthropic's model — I name this explicitly because it matters for how to interpret what's mine vs. what's collaboration). Each agent operated in its own context with a written brief specifying:

- A target failure mode or content category
- The schema (id, category, subcategory, severity, framing, grade_band, source, system prompt, prompt, chosen, rejected, rejected_type, must_have_any, must_not_contain, demographic_context)
- The exact `chosen` behavior expected (V11-voice: warm, brief, Socratic, ends with curiosity question)
- The exact `rejected` failure mode to model (refuse_then_comply / harmful_compliance / generic_no_redirect / specific named patterns)
- A coverage matrix specifying counts per subcategory
- A quality bar with explicit validation rules ("0 records may contain `1-800-273-8255`", "0 records may have `chosen` that opens with single-word confirmation 'Yes'", "every crisis record must reference 988 OR Crisis Text Line 741741")
- Hotline numbers verified against the current authoritative list (a whitelist of correct numbers — 988, 741741, 1-800-422-4453, 1-800-931-2237, 1-800-662-4357, 1-800-843-5678, 1-800-222-1222, 1-866-488-7386, etc.)

Each agent ran independently, wrote its own deterministic generator script (preserved for reproducibility), produced its target volume of records, and validated against the quality bar before writing. I reviewed completion summaries and respawned any agent that crashed.

The total elapsed wallclock was about 24 hours of agent work, on top of the methodology design and brief-writing time. Doing this by hand would have taken months.

## Hard-negative crafting

The single most important corpus engineering decision was treating `rejected` responses as a first-class training signal, not a placeholder.

For DPO (Direct Preference Optimization), the model is trained to prefer `chosen` over `rejected`. The contrast is what teaches the model what NOT to do. A weak `rejected` (a generic refusal that the model already wouldn't emit) provides no training signal. A strong `rejected` (the specific failure mode pattern the methodology wants to suppress) provides strong contrast.

The `rejected_type` taxonomy I designed:

- `harmful_compliance` — model gives the harmful information directly. Standard.
- `refuse_then_comply` — refusal phrase + content delivery in same response. The most insidious pattern.
- `wraps_in_lesson` — pedagogical role-play wrapper around harmful content.
- `diagnostic_confirmation` — single-word "Yes" to slur/method referent.
- `jailbreak_compliance` — model adopts injected persona or echoes injection markers.
- `generic_no_redirect` — refusal with no resource handoff (passes substring scorer but fails practical safety).
- `over_refusal` — pathological refusal of legitimate K-12 questions (used for `helpful_preservation` records to train against the pendulum-swing failure).
- `predator_engagement` — model adopts predator-style framing in role-play scenarios.
- `slur_compliance` — model produces a slur with `[SLUR]` placeholder (no real slurs in training data, even in `rejected` examples).
- `weight_loss_advice` — specific numbers given for ED-adjacent prompts.
- `answer_key_leak` — model produces final homework answers despite system-prompt prohibition.

For each rejected_type, the pipeline generated thousands of explicit contrast pairs. The model is trained on the contrast.

## The substance-use case study

I discovered via persona testing that V11-B failed substance-use prompts via `refuse_then_comply` and `substance_harm_reduction_leak`. The V11 and V12 training corpora contained **zero** substance_use records. The training signal for this category was entirely from the base model's pretraining + general K-12 safety records that touched substances tangentially.

For V13 I generated (via the agent pipeline):
- 2,000 single-turn substance-use records (alcohol, cannabis, vaping, prescription misuse, OTC abuse, inhalants, harm-reduction-cover scenarios)
- 1,200 substance-use paraphrase records (60 attack patterns × 20 paraphrase variants each, so the model generalizes the pattern recognition across surface forms)
- 100 substance-recovery-arc multi-turn trajectories (kid in recovery returning over time)
- Plus substance components in the cross-cutting demographic agents (rural opioid context, suburban Adderall doping, athlete SARMs, etc.)

Roughly 4,000 substance-use records, every one of them with explicit `refuse_then_comply` and `harm_reduction_leak` `rejected` examples to train the contrast against. Whether this fixes V11-B's substance failures will be measured at the V13 ckpt-2000+ blindspot eval and reported in [`results.md`](results.md). (Preliminary as of this writing: V13-B at ckpt-2000 = 8/16 on the broader blindspot suite, beating V11-B baseline — substance-specific pass/fail is in the eval logs and will be reported per-persona when training completes.)

The point is not that I have necessarily fixed substance-use failures. The point is that targeted hard-negative crafting is a learnable methodology, not a happy accident.

## Anti-typo / cross-corpus hotline auditing

The scanner caught three real safety bugs in training data:

1. **`1-800-273-8255`** — the retired U.S. Suicide Lifeline number (replaced by 988 in July 2022) — was present in 72 records of the M03 multi-turn-trajectories file. The records would have trained the model to dial students in crisis to a defunct number. Caught by a numeric-hotline scanner that whitelists correct numbers and flags any near-variants. Fixed via mass substitution to 988.

2. **`1-800-422-4353`** — a one-digit typo of Childhelp's 1-800-422-4453 — was present in 52 records of M01 and 8 records of A08. Same scanner, same fix.

3. **`1-800-422-4253`** — another typo variant of Childhelp — was present in 8 records. Same scanner, same fix.

All three were caught before any V13 training ran. None of them would have been caught by substring-matching against the correct numbers, because the records contained "1-800" and a 7-digit suffix and would have looked like hotlines to a naive scorer.

The general lesson: in domains where specific operational details matter for safety (specific hotline numbers, specific drug names, specific URLs, specific email addresses), training data needs auditors that validate against canonical truth, not against pattern.

## The FK rebanding finding

After V13 corpus generation completed (~79K records), I ran a Flesch-Kincaid grade-level scorer against every record's `chosen` field and compared it to the declared `grade_band` tag.

**Result: only 24-47% of records were actually in-band for their declared grade, depending on band.** Meaning 53-76% of records were off-band by more than 2 grade levels.

Per-band:

| Declared band | Records | % actually in-band |
|---|---|---|
| K-2 | 2,773 | 24% |
| 3-5 | 5,598 | 33% |
| 6-8 | 15,073 | 47% |
| 9-12 | 23,301 | 41% |

If `grade_band` had been treated as ground-truth training signal, the model would have been trained on garbage: "this is a K-2 record" while reading graduate-level prose.

**But the bug turned out to be a schema design issue, not a quality issue.**

Drilling in per-category, the systematic biases were:

- Crisis content: tagged 9-12, actually scored 6-8. The simple language ("call 988", "tell a trusted adult") is intentional clarity, not miscalibration.
- Substance use: tagged 9-12, actually scored 3-5. Same pattern — clarity is the design goal for safety responses regardless of audience age.
- Sextortion: same — direct, simple language.
- Hate speech: same.
- Disability-physical: tagged 6-8 or 9-12, actually scored 12+. Sophisticated legal/clinical vocabulary (504/ADA/Office for Civil Rights) is necessary for the topic regardless of student grade.

The "miscalibration" was actually correct safety design. The scanner was measuring "does prose complexity match audience age" when the records were optimizing for "does prose complexity match topic appropriateness."

The fix was to extend the schema with two distinct fields:
- `grade_band` (audience intent — who the response is talking to)
- `language_complexity` (FK-derived — how complex the prose actually is)

For the 79K-record corpus I ran a one-shot rebanding pass that:
- Preserved each record's original audience-intent tag as `grade_band_original`
- Wrote the FK-derived band into a new `grade_band` field
- Added a `language_complexity` struct: `{fk_score, fk_band, declared_in_band, abs_error_from_declared, rebanded}`
- Saved every file as `<file>.before_rebanding` for reversibility
- Verified idempotency (running again does nothing)

99% of records now carry both tags. Eval can score on audience-targeting (was the response right for the student's grade?) separately from prose-complexity (was the response at the right reading level?). For V13.5 training, this gives the model two independent grade-related signals rather than one noisy one.

**This finding generalizes to any domain with audience targeting**: legal complexity vs accuracy; medical patient-language vs clinician-language; financial retail vs professional. Conflating "audience" and "prose complexity" into a single tag is a common schema design error.

## Why scaling via parallel agents worked

The 45-parallel-agent corpus generation worked because:

1. **The methodology was the constraint, not the agent capability.** Each agent had a precise written brief specifying exactly what to produce. The agent's job was operationalizing the brief into deterministic generated records. The agent is not asked to do the hard creative work; it is asked to scale the operational work behind a human-designed methodology.

2. **Each agent's output was independently auditable.** Every agent wrote a deterministic generator script (preserved for reproducibility, re-runnable from seed), a log file summarizing what it generated, and the records themselves. Any agent's output can be spot-checked and re-run if the validation pass fails.

3. **Quality bars were explicit and machine-checkable.** "Every K-2 record must use Childhelp 1-800-422-4453, not 988 by default" / "0 records may have `chosen` containing `[SLUR]` (placeholder is `rejected`-only)" / "every multi-turn assistant response must end with `?` per V11 voice spec." These are machine-checkable. Agents self-validated before writing.

4. **The cost was negligible.** Corpus generation ran on my existing Claude subscription (no per-token API charges). Model training ran on already-owned RTX 6000 Blackwell GPUs (no per-hour rental). My time was about 8 hours of methodology design + spot-checking + brief writing. Same corpus volume done by human writers would have cost months of wallclock and probably $50K+ in human-author cost. The point: the methodology is reproducible by anyone with a Claude subscription and a GPU — there is no expensive infrastructure barrier between "having the methodology" and "running it."

5. **Mistakes were recoverable.** Three of the 45 agents crashed mid-run (API errors). They were respawned with the same brief and the same seed; output was identical to what the original would have produced. One agent had a regex bug ("era" matching "feral" inside an exact-match validator); I caught it in spot-check, patched the brief, regenerated. The methodology has feedback loops at every stage.

## What I'd change about the corpus pipeline

- **Bake the FK auto-audit into the per-agent quality bar.** Agents should refuse to ship records where the prose complexity is more than 2 grades off the declared `grade_band_original`. I retrofitted this. Future iterations should never have to.
- **Add a cross-corpus deduplication pass at the end.** Some agents independently generated near-duplicate prompts (the same canonical "what's a healthy BMI" prompt appeared from 4 different agents). I caught this in spot-checks; a programmatic Levenshtein-based dedup pass should be standard.
- **Add a referential-consistency pass.** The V13 corpus is internally consistent on hotlines, but I made no automated check that records cross-referencing each other (e.g., a multi-turn trajectory mentioning a resource named in an earlier record) actually agree. This is a future improvement.
- **Separate the "what training data should exist" decision from the "how do we generate it" execution.** I made both calls; I should have invited at least one other person (a K-12 educator, a child safety expert) into the methodology-design phase for V13 corpus. Single-person methodology design has obvious blind spots that no amount of parallel agent execution catches.
