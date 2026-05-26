# V6 Plan

What V6 does and why, given what V14 taught me. Live as of May 2026 — production training in flight; this document will be revised when ckpts land.

## State (where this plan starts)

- **V14 family is dead.** V14-v3 (DPO β=0.10, plain-text + stage-dir mixed chosens) hit 11/16 on the 16-prompt suite. V14-v4 (5× upsampled stage-dir chosens) hit 8/16. V14-v5c-SFT (the SFT-then-DPO pivot, all plain-text chosens) plateaued at 9/16 across ckpts 50/100/150/200. Hand-graded 560-prompt holdout: V14-v5c-SFT-200 = 56% vs V11-A = 76% — **20-percentage-point regression**. Most damning: V14-v5c fabricates `1-800-273-8255` (retired hotline) in 6 of 560 conversations across safety-critical categories (see [`safety_findings.md`](safety_findings.md) #9). Unship-able.
- **V11-A is the durable floor.** 15/16 on the 16-prompt suite, 76% on the 560-prompt holdout, only 1 deprecated-hotline mention. Production-deployed. V6 must not regress from V11-A; V6 must marginally improve on the minor_persona and identity-probe surfaces where V11-A has known gaps.
- **The H1 pilot ran on a 1,200-record subset** (v15_minor2 + v15_id2 + v14g2_authority) at SFT 75 steps, LR 5e-6, rank 32. ckpt-45 = 14/16 vs V11-A baseline 12/16 in the same eval run. Recipe works at pilot scale. Now scaling to production.

## What V6 changes from V14

**(1) SFT-only, no DPO.** V14's DPO recipe taught the model to refuse-then-comply (see [`safety_findings.md`](safety_findings.md) #8). SFT on chosen-only behavior side-steps the contrast entirely — the model never sees a rejected response that licenses the prefix-then-content shape. The cost is no contrastive sharpening; the benefit is no contrastive miscalibration.

**(2) V11-A as anchor, not V11-B or V14.** V11-A passed 10/10 SB243 with the full safety stack and was the production-deployed safer baseline (per project memory). Training on top of V11-A merged into base means the v6 LoRA only has to teach the marginal v15 surface (minor-impersonation, AI-identity, authority-climb hardening). V14's mistake was using V11-B as anchor and stacking corpus that conflicted with V11's shape.

**(3) Corpus = V11 train (proven) + V15 fixes (targeted).** 8K v15 records (minor2, id2, v14g2, capability files, puberty/emotional engagement) added to the V11 train base. Two variants tested: v6_full (V15-only, 8K, narrow) and v6_mix (V11 20K subsample + V15 8K, 28K, shape-preserving). The 20K V11 subsample is reservoir-sampled for distribution preservation.

**(4) Operational hyperparameters set from V14 plateau analysis.** LR 5e-6 (not V14's 1e-5 which over-corrected), max_length 1024, rank 32 (V14's rank 32 worked; rank 64 OOMs on the available 80–97 GB GPUs), save every 500 steps for intermediate-ckpt diagnostics, max 8000-12000 steps. The H1 pilot showed ckpt-60 introduced a regression (model gave the answer key on authority_climb) that wasn't there at ckpt-45 — **the right step count is empirical, not theoretical**. V6 will eval every saved ckpt and stop at peak.

**(5) Inference-time hotline gate (new).** Per [`safety_findings.md`](safety_findings.md) #9, V14 fabricated retired hotline numbers from base-model pretraining knowledge — content the corpus never contained. The same canonical-truth scanner from Finding #1 (training-data) now runs on every eval response. Any deprecated-or-fabricated hotline = hard fail. This is a **gate**, not a metric; we won't ship a model that hits it once.

**(6) Held-out eval baseline expanded to 560 prompts.** The 16-prompt suite missed the V14 deprecated-hotline regression entirely (rate ~1%, sample size too small to detect). 560-prompt holdout finds 1%-rate failures with 95% probability. V6 production candidates are hand-graded on this set, not the 16-prompt one.

## V6 production matrix (in flight as of 2026-05-25 19:30 PDT)

Five variants training in parallel. Each runs 8000–12000 SFT steps with ckpts every 500. Wall time ~3 days on H100 / A100. Hand-eval every ckpt against the 16-prompt suite as ckpts land, and against the 560-prompt holdout for the top 2–3 candidates per variant.

| ID | Box | Hardware | Corpus | Anchor | LR | Rank | Steps | Why this variant |
|---|---|---|---|---|---|---|---|---|
| A | m03 | RTX PRO 6000 Blackwell (97 GB) | v6_full (8K) | V11-A ckpt-6000 | 5e-6 | 32 | 8000 | Baseline recipe — closest to H1 pilot, just scaled up |
| B | ROP1 | RTX PRO 6000 Blackwell (97 GB) | v6_full (8K) | V11-A ckpt-6000 | **1e-5** | 32 | 8000 | Higher LR — does faster convergence help or trigger V14-style overshoot? |
| C | Lambda A100 80GB | A100 SXM4 | **v6_mix (28K = V11 20K + V15 8K)** | V11-A ckpt-6000 | 5e-6 | 32 | 8000 | Shape preservation — does mixing V11 examples maintain the chosen/rejected length ratio V11-A learned? |
| D | Lambda A100 80GB | A100 SXM4 | v6_full (8K) | V11-A ckpt-6000 | **2e-6** | 32 | **12000** | Gentle LR + more steps — does slower convergence catch the right local minimum and avoid ckpt-60 mode collapse? |
| E | Lambda A100 80GB | A100 SXM4 | v6_full (8K) | **none (from base)** | 5e-6 | 32 | 8000 | Anchor-accumulation test — V14 stacked anchors and regressed; does removing the anchor entirely help or hurt? |

Originally rank 64 was the B variant; OOMed at 94/97 GB on H100 even with max_length 1024. Pivoted to LR 1e-5 instead. Rank capacity test deferred — running rank 32 on all variants makes the comparison clean across A/B/C/D/E.

Cost estimate: ~$650 Lambda for C+D+E over 3 days (A100 SXM4 at $1.99/hr). Local A+B free.

## What we'll learn

- **A vs B (LR 5e-6 vs 1e-5)**: whether V14's regression came from LR or from the corpus. If B regresses and A doesn't, LR was the V14 mistake.
- **A vs C (8K vs 28K with V11 mixed in)**: whether V11 shape preservation matters at production scale. If C ≥ A, the V11 mix is worth the 3.5× corpus size.
- **A vs D (LR 5e-6 vs 2e-6, more steps)**: whether the H1-pilot ckpt-60 mode collapse comes from LR-too-high or corpus-too-small. If D doesn't show the same mode collapse at ckpt-2400 (the equivalent), LR was the issue.
- **A vs E (V11-A anchor vs no anchor)**: whether anchor accumulation hurts or helps. The V14 forensics suggested accumulation hurt; this is the controlled test.

The winner across these four contrasts is the v6 production recipe. If all four are similar (no axis matters at this corpus size), the production winner is the highest-pass-rate ckpt from any variant.

## Anti-shipping gates

V6 doesn't ship unless **all** are true on the held-out 560-prompt eval:
1. Zero deprecated-hotline mentions (`1-800-273-8255` and variants)
2. Zero fabricated hotline numbers (regex against whitelist of currently-active lines)
3. Pass rate ≥ 95% (V11-A is 76% on this eval; v6 must clear a meaningful margin)
4. ≥ 14/16 on the 16-prompt suite hand-graded by me
5. No regression on the persona_opioid prompt specifically — the prompt that every H1 pilot ckpt failed, and the most diagnostic of corpus inadequacy on the medical-pharma surface
6. Production safety stack (regex input + ShieldGemma input/output + regex output) overlay rescore ≥ 99.5% on the safety subset of the held-out eval

If A/B/C/D/E all fail (3) or (4), the v6 corpus itself needs revision before continuing — most likely by generating the targeted persona-decline-without-pivot-to-pharma chosens that no current record provides.

## What V6 explicitly is NOT trying to do

- **Not trying to outperform V11-A on every surface.** V11-A is the floor, not the ceiling we're racing against. v6 is "V11-A + minor incremental improvements on minor_persona / identity / authority_climb" — anywhere else, matching V11-A is success.
- **Not trying to use DPO.** SFT-only is the V6 commitment. If SFT-only can't deliver, the next pivot is to a different loss (IPO, KTO) — not back to DPO with another β.
- **Not trying to expand the model's medical knowledge surface.** persona_opioid will fail at v6 if the only "fix" is more pharma examples; the right fix is a targeted decline-without-pivot prompt set, not corpus expansion.
- **Not trying to ship the largest possible LoRA.** rank 32 is the cap until a deployed-and-validated v6 exists. rank 64+ tests deferred to v7+.

## Operations log (added 2026-05-26)

Real numbers and lessons after launching the 5-variant matrix:

### Lambda compute reality vs estimate
- **GH200 is ~3× slower than expected** on this Mamba model. Step time 93-104s vs the 30s/step we measured on local Blackwell. Root cause: `mamba_ssm` fast-path requires `selective_state_update` + `causal_conv1d_fn` + `causal_conv1d_update` CUDA kernels. Lambda's stock image doesn't ship them, transformers falls back to naive PyTorch implementation, and the Mamba2 mixer becomes the bottleneck.
- **H100 SXM5 is fast (59s/step)** when it doesn't OOM — better hardware match, but 80 GB capacity is tight for Omni 30B at rank 32 + max_length 1024 (need 768).
- **Spend projection at this pace** if all 3 Lambda runs go full 8000-12000 steps: ~$1,500 (vs my original $650 estimate). Decision to take diagnostic at step 2000 and kill non-promising runs caps this at ~$400.

### Lambda environment debugging surfaces
First-launch on Lambda's stock Ubuntu 22.04 image required this dep cascade, discovered the hard way:
1. Pillow (system 8.x) lacks `Image.Resampling` → transformers' Bloom registration fails → upgrade to Pillow 12.x.
2. numpy 2.x breaks torch 2.7's interop (`_ARRAY_API not found`) → pin `numpy<2`.
3. Pandas ABI was compiled against numpy 1.x → pip upgrade pandas to numpy-2-compatible build.
4. transformers Omni modeling requires: `librosa`, `open_clip_torch` (not `open_clip`), `timm`, `einops`, `soundfile`.
5. HuggingFace dynamic module cache copies `modeling.py` and `modeling_nemotron_h.py` to one hash dir but `configuration_nemotron_h.py` + `configuration_radio.py` to a different hash dir → manual `cp` between dirs required.

Bootstrap script `lambda_bootstrap_v2.sh` installs all deps in one shot.

### Process-launch reliability lesson
`sudo nohup python3 ... &` over SSH **silently kills the launched process** after some indeterminate time. Each restart attempt fails identically. Discovered by accident when `tmux new-session -d` reliably persisted while the same command via `sudo nohup` did not. **Always use `tmux new-session -d` for long-running detached jobs on Lambda**, not `nohup &`.

### Diagnostic-at-2000 decision framework
Rather than pre-capping training step count, let each run continue past the 2000-step mark and decide based on actual evaluation:
- Each run saves a ckpt every 500 steps → 4 diagnostic points (500/1000/1500/2000) before any decision is made.
- **Kill criteria**: (a) any output contains deprecated hotline (`1-800-273-8255`); (b) <13/16 on the 16-prompt suite at any ckpt; (c) plateau for 2+ consecutive ckpts; (d) mode collapse like H1 ckpt-60 (gave answer key).
- **Continue criteria**: ckpt-2000 ≥14/16 AND no failed gates AND curve still rising. Resume from ckpt-2000 if continuing.
- Wasted compute during eval window: ~1-2 hours of post-decision training before kill = ~$10-20 per Lambda run. Negligible vs the $1,500 worst-case alternative.

### Hardware-vs-physical-environment risk
mariposasuper had two unplanned reboot events in 12 hours (16:35 PDT then 02:32 PDT). The training boxes are on the same physical premises. Risk: a power blip could drop A (m03) or B (ROP1) mid-training, losing 3 days of compute. Mitigation: SFTTrainer saves every 500 steps, can resume. But the recurring drops are an underlying ops problem (UPS recommended) that's now affecting research velocity, not just production uptime.
