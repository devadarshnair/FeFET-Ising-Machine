# Stage 3.0 results: local screening of the round-2 hooks (tuning-only, exploratory, not confirmatory)

Code: commits through `48fd072`; runner `scripts/testing/run_s1.py` (string cfg and R keys added), job lists `scripts/testing/s3_0_jobs.py`, energy screen `scripts/testing/s3_reprice.py`, summaries `analyse_s30.py`. Evidence: `s3_0_reprice.md/json`, `s3_0_evidence/` (tables, job lists, logs, JSONL archive).
Setup: local, local job queue, one heavy job at a time (about 14 h of single-core time in total). Instances are **tuning-only**: p3 keys 2101-2112 (tag 10), Max-Cut `R5001-R5005` (fresh generator, no reference built). Base arm = the Stage 2 ours_new (c 0, K 0.25n, L = 10). Every hook got the same effort: two settings (one for single-setting hooks), same instances and seeds, no per-hook tuning. 36 runs per robustness cell, 24 per p3n480 cell, 12 per p3n960 cell, 10 per Max-Cut cell: CIs are wide (about +-0.2 at 24 runs), so a hook that "does nothing" is "no signal", not "proven useless". Kill rules were stated in `STAGE3_PLAN.md` section 3 (and the p3n480 no-regression margin of -0.15 was fixed before any 960 job started).

## 1. Stage 3.0-A: energy re-pricing of the stored Stage 2 records (zero new simulation)
ETS99 ratio ours_new / comparator, nominal, p3n480, 64 x 3, corrected pricing, B = 2000, verdict by the H8 rule without Holm. B3 is given the same tweak (t6 gating included, the conservative choice).
| configuration (all on top of the corrected pricing) | vs B3_sel [CI] | vs B3_h8 [CI] | ours / B3_sel energy per run (fJ) |
|---|---|---|---|
| base (Stage 2) | 1.48 [0.95, 2.12] | 1.23 [0.84, 1.68] | 8.12e11 / 5.27e11 |
| t1 incremental field | 0.90 [0.58, 1.29] | 0.75 [0.51, 1.02] | 4.91e11 / 5.27e11 |
| t2 sparse storage (ours only) | 1.32 | 1.10 | 7.25e11 / 5.27e11 |
| t3 64-row tiles | 1.93 [1.25, 2.77] (loss) | 1.61 (loss) | 1.06e12 / 5.27e11 |
| t4 skip read after reject | 1.37 | 1.14 | 7.38e11 |
| t5 overlap read with select | 1.27 | 1.06 | 6.96e11 |
| t6 lane clock gating (every machine) | 1.36 | 1.13 | 6.25e11 / 4.36e11 |
| b3b idle sees SAR savings | 1.46 | 1.22 | 8.01e11 |
| t1 + t5 | 0.72 [0.47, 1.04] | 0.60 [0.41, 0.82] | 3.97e11 / 5.27e11 |
| **t1 + t5 + t6 (B3 also gated)** | **0.64 [0.42, 0.92]** | **0.54 [0.36, 0.73]** | 2.95e11 / 4.36e11 |
| t1 + t5 + t6, B3 NOT gated (favourable-to-ours bound) | 0.54 [0.35, 0.77] | 0.45 [0.31, 0.61] | 2.95e11 / 5.27e11 |
| t1 + t5 + t6 + b3b | 0.64 | 0.54 | 2.95e11 / 4.36e11 |
p4n480 gives the same ordering (t1 + t5 + t6: 0.47 against B3_sel). The H8 evaluator labels most rows "inconclusive" even where the ETS interval lies below 1 (0.54 [0.36, 0.73] against B3_h8) because the win rule also requires the success-difference lower bound to be above -1 pp, which 192 runs cannot establish at success parity (STAGE3_PLAN review concern 3). Reading: **the architecture tweaks T-1 (with T-5, T-6) are the only lever that moves the primary energy question from "no advantage shown" to a plausible advantage**; T-3 is harmful; T-2, T-4, b3b are small. The re-pricing prices T-1 as an ideal-device exact incremental field and without refresh or screening hardware, so it is an upper bound until 3.0-B1 and the priced robustness hardware are included (3.1).

## 2. Stage 3.0-B1: robustness and T-1 exactness (p3n240, nominal, 12 instances x 3 seeds = 36; ideal level 0.92)
| arm (mitigation) | share 0, k = 1 | share 0.03, k = 1 | share 0.25, k = 2 |
|---|---|---|---|
| registered stack M0 (Stage 0 / 1 data: 0.02 / 0.50 / 0.00; same keys, different seeds) | 0.02 | 0.50 | 0.00 |
| + leaky-zero screening (scr5) | 0.92 | 0.92 | 0.92 |
| + per-cell correction (lcor8) | 0.89 | 0.92 | 0.89 |
| + screening + correction | 0.92 | 0.92 | 0.92 |
| sparse storage, plain wv+cal column (no differential partner) | 0.92 | 0.92 | 0.92 |
| no-diff dense wv+cal (control) | 0.00 | 0.00 | 0.00 |
| T-1 incremental field, refresh 50, no screening | 0.00 | 0.47 | 0.00 |
| T-1 refresh 50 + screening | 0.89 | 0.92 | 0.92 |
At the working point (share 0.5, k = 1) T-1 with refresh 0, 50 and 200 and the base all give 0.92. So: **screening, per-cell correction and sparse storage each remove the C2C-share cliff in this cell**, including the k = 2 / share 0.25 point where the registered stack scores 0; **T-1 alone is not robust** (it collapses where the registered stack collapses, and at k = 2) and needs screening to keep its exactness; sparse storage works without the differential column, i.e. at lower mitigation cost than the registered diff stack. Caveats: one cell (p3n240), 36 runs, the cliff-model of this simulator (the C2C share is unmeasured), and screening / correction costs are priced but their hardware is estimated.

## 3. Stage 3.0-B2: barrier and acceptance hooks at p3n480 (ideal, 8 instances x 3 seeds = 24; base 0.83)
| hook (setting) | success [Wilson] | mean best_E | kill rule (>= 0.68) |
|---|---|---|---|
| base | 0.83 [0.64, 0.93] | 0.21 | - |
| esc A / B (RNG-free escalating offset) | 0.79 / 0.79 | 0.25 | pass |
| burst A / B (stall burst accepting gain >= -up) | 0.71 / 0.71 | 0.33 | pass |
| adaptive L, m = 3 / 6 (R7) | 0.71 / 0.08 | 0.29 / 2.04 | A pass, B killed |
| cc burst / cc always (configuration checking) | 0.67 / 0.04 | 0.33 / 2.46 | killed |
| colour-parallel commits | 0.58 | 0.50 | killed |
| breakout weights A / B | 0.00 / 0.46 | 23.9 / 4.71 | killed |
| conflict kicks A / B; late acceptance 50 / 200 | 0.00 (all four) | 5.8-73 | killed |

## 4. Stage 3.0-B3: survivors at p3n960 (ideal, 6 instances x 2 seeds = 12; tuning-only)
| arm | success [Wilson] | mean best_E |
|---|---|---|
| base (c 0, K 0.25n) | 0.08 [0.01, 0.35] | 1.17 |
| B3_sel (tuned on p3n480; not retuned at 960) | 0.25 [0.09, 0.53] | 1.25 |
| **adaptive L, m = 3** | **0.58 [0.32, 0.81]** | 0.67 |
| burst B (K 0.1, len 0.1, up 3) | 0.33 [0.14, 0.61] | 1.17 |
| esc A | 0.33 [0.14, 0.61] | 0.92 |
| burst A | 0.08 [0.01, 0.35] | 1.25 |
Newcombe differences (12 vs 12 runs): adaptive m = 3 vs base **+0.50 [+0.12, +0.73]**; vs B3_sel +0.33 [-0.05, +0.61]; burst B / esc A vs base +0.25 [-0.08, +0.53]. **First hook that lifts the 960-spin cell**: R7 (adaptive multi-scale kick size, a few-bit counter and shift) is the only one whose interval excludes zero against the base; it is a screening lead at n = 12 on one instance family (p3), with a poor setting (m = 6) that fails at 480, so it needs tuning and a confirmatory test before any claim. The Stage 1 conclusion "960 is a greedy ceiling" (A3) is not supported for this hook; B3 is not yet clearly beaten and was not retuned at 960 (equal-effort tuning is Stage 3.1).

## 5. Stage 3.0-B4: Max-Cut on fresh R graphs (ideal, 5 graphs x 2 seeds = 10 runs; mean best_E = -cut; reference SA about 6641 on R5001)
Base (c 0.08, K 0.5n, Stage 1 gk selection): -6629.9 (sd 12.9); ours_none (tuned T): -6625.3; B3 (colouring-selected configuration, not tuned for Max-Cut): -6617.9; conflict kicks -6637.5, cc always -6634.6, esc -6629.9, burst -6624.5 / -6625.6, cc burst -6627.4, adaptive -6621.5 / -6622.1, colour-parallel -6616.3; late acceptance -6554 / -5919; breakout weights -6135 / -6452. **Every arm that works is within about 0.2 % of the base (one run-sd is 0.2 %): no hook gives a Max-Cut signal.** All working arms reach the 0.99 x reference target (success saturates, as on G43-47), so on this random-graph class Max-Cut is an energy-to-target comparison. The harder planar G51-54 class (where H8 lost) has no fresh instances.

## 6. Decisions this screen supports (see STAGE3_PLAN.md)
1. **Worth paying for:** the energy stack T-1 + T-5 + T-6 with screening (or sparse storage), tested confirmatory at 480; the R7 adaptive-L lead at 960 (tuning first, then confirmatory); P4-1 tuning (cheap).
2. **Not worth paying for (killed or no signal):** breakout weights, late acceptance, conflict kicks, configuration checking, colour-parallel commits, RNG-free escalation (no gain), T-3, and all Max-Cut algorithm hooks.
3. **Scope:** with the R7 lead the 960 cell is no longer a "likely loss to be dropped": scope B (480 + Max-Cut + p3n960) is recommended; scope C (p4n960) only if p4n960 tuning shows the same lead.
4. Open and exploratory: all of the above are tuning-instance screens; the energy re-pricing used the confirmatory Stage 2 records only as counters (no Stage 2 result is re-analysed); two settings per hook is not a tuned comparison; the p3n960 screen is 12 runs.

## 7. Deviations and notes
The first sparse-storage jobs failed (the simulator asserts that sparse storage has no complement partner): rerun with the plain wv+cal mitigation and a no-diff control; no other job failed. The B3 comparator in the Max-Cut and 960 screens used its Stage 1b colouring selection (not retuned for those cells). `analyse_s30.py` reports success only for colouring (Max-Cut success is undefined without a built reference).
