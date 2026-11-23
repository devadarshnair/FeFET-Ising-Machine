# Stage 1 results (tuning pilots on cloud 16 vCPU; DRAFT analysis, tuning-only, not confirmatory)

Return `00_admin/s1_return/20261121T200310Z_stage1` (checksums verified), pin `d7d178a` (worktree clean). Unpacked into a fresh directory (`analysis_stage1/`) and the registered
`select` (stages 1a and 2) and `report` steps were re-run locally (`run_s1.py`): **both selection files are byte-identical to the cloud output**; the report differs only in its directory line.
Evidence committed in `s1_evidence/` (selections, gate, field MC, tables, queue log, raw JSONL archive); tables are produced by `scripts/testing/analyse_s1.py`.
All numbers are success on the tuning instances (tag 10: planted p3 keys 2101-2112, `gk` = G43-47) at 16-18 runs per cell: Wilson 95 % CIs are wide (about +-0.2). **No energy (ETS) was computed in Stage 1; every statement below is about success.**
Nothing beyond the registered selection/gate rule was used to pick configurations.

## 0. Run facts
320/320 jobs done, 0 failed; gate `0.5.r13_960` took 712 s; makespan 79.6 min (18:43-20:03 UTC) against 143 min simulated for 16 slots; measured 18.8 CPU-h (estimate 33.4 incl. x1.3 margin). Cost at Rs 32.14/h including set-up and gate: about Rs 60.
Measured s/run (16 vCPU): ours ideal p3n480 9.8, p3n960 65, gk 18; ours nominal tiled-256 p3n480 34, gk 93; B3 p3n480 6.7, p3n960 32, gk 9; B1 nominal p3n480 50, gk 174; B1 bit-sliced p3n240 12.7.

## 1. R13 identity at N = 960 (hard gate): PASS
Fresh ideal vs tiled-256 nominal (wv+diff+cal, C2C share 0.5) runs of the same registered ours_kc2_i11 spec, p3n960 key 2101, 2 records: **best_E and the whole energy curve identical** (2 vs 2, 5 vs 5; 529 920 and 576 000 flips identical). Under the tiled simulator, nominal == ideal at N = 960 (it was 0/40 identical under the one-column model in H8).
Limits: 2 records of one instance; share 0.5 only (the identity says nothing about the cliff region).
Field MC (10 draws x 20 states, p3n480, share 0): tiling lowers the nonzero field-error fraction from 44.1 % to 35.5 % (sd 1.16 -> 1.03, mean +0.18 -> +0.07): a modest variance reduction, not a removal.

## 2. Registered selection and gate
Rule (prereg/hw/S1_tuning_grids.json): highest pooled success, ties by lower mean best_E, ties by grid order; round 1 ranks on p3n480 (colouring) and gk; round 2 only on p3n960 (top 4 of every arm plus one extra `ref` row for ours); gate = ours improves on the registered reference by >= +0.15 at p3n960 or >= +0.25 on gk with a Newcombe lower bound > 0.
**Selected configurations (equal tuning: 12 labels per arm in round 1, top 4 in round 2):**
| arm | colouring (p3n480 round 1) | success (n = 16) | gk (G43-47) |
|---|---|---|---|
| ours_kc2_i11 | c = 0.04 (L = 20), K = 0.5n | 0.75 [0.51, 0.90] | c = 0.08 (L = 80), K = 0.5n |
| B3_v2 | p90/5, final-temperature knob 0.5 | 0.75 [0.51, 0.90] (tied with p90/10) | p75/5, knob 0.5 |
| ours_kc2c | tfinal 0.5, K = n, c = 0.04 | 0.56 [0.33, 0.77] | tfinal 0.5, K = n, c = 0.04 |
| ours_none (= B1_best ideal, A6) | p90/5, schedule fraction 0.5 | 0.25 [0.10, 0.49] | p75/5, fraction 0.5 |
Registered references (ours, c = 0): p3n480 K = 2n 0.25 [0.10, 0.49], K = n 0.31, K = 0.5n 0.44; gk K = n 0.27 [0.11, 0.52], K = 2n 0.20.
**Gate outcome (relabelled after review review): formal PASS via a non-informative tuning-only cell (gk); substantive FAIL at p3n960.** The registered file says `stage2_go = true` because the gk branch passed. gk: selected 1.00 [0.80, 1.00] vs reference 0.27, difference +0.73, Newcombe lower bound +0.41 (pass). p3n960: selected 0.17 [0.06, 0.39] (3/18) vs reference 0.00 [0.00, 0.18]: difference +0.17, Newcombe lower bound -0.04 -> **fail**. The 1b variant rule selected no variant (none beat `base` by +0.10).

## 3. Which fixes helped
| item | result | verdict |
|---|---|---|
| **R4 kick size + K** | p3n480: best 0.75 (c = 0.04, K = 0.5n) vs 0.25 for the registered (c = 0, K = 2n), +0.50; also +0.13 from K alone (K = 0.5n at c = 0: 0.44). gk: c >= 0.04 reaches 1.00 vs 0.27 (L = 10, K = n). p3n960: best 0.17 vs 0.00 for the reference; L = 77 (c = 0.08) gives 0.00. In Researcher A's 3-seed ablation p3n480 showed no gain; here it does: a larger kick *combined with a shorter stall window* is what works. | **helps** at 480 and gk; marginal at 960 (not significant) |
| **R6 tabu** | p3n480 (rank-1 config): base 0.75, tabu 0.5 0.56, tabu 1 0.31, tabu 2 0.00; p3n960: base 0.17, tabu 1 0.00; gk: all 1.00 (mean cut slightly better with tabu 2, -6629 vs -6623, no significance claim) | **hurts** (predicted to help; the re-flip diagnostic found the mechanism but a tabu mask is not the cure) |
| **R5 targeted kick** | p3n480: R5 0.62, R5+tabu 1 0.69, R5+tabu 2 0.44 vs base 0.75; p3n960: R5+tabu 1 0.00 | **no gain** (and not registered as a design contribution) |
| **R10 dither** | share 0 / 0.01 / 0.03 at k = 1, p3n240: 0/60 each; matched Metropolis control (T = 1, exact field) also 0/60 | **hurts; control equally fatal**: both noise injections at the LSB scale destroy the plateau walk, so R10 cannot be separated from "I11 as a low-T anneal", and neither helps |
| **R9 reference column, R11 op-point calibration** | p3n480 tiled, share 0.03: M0_tiled 0.06, +R9 0.06, +R11 0.00 (n = 18 each); share 0: all 0.00 | **no signal** (power: 18 runs cannot resolve differences below about 0.4); field-level tiling effect in section 1 |
| **R12 Max-Cut hybrid** (gk, 25 runs) | ours_none (tuned T) 1.00, I11 + Metropolis T = 1 1.00, hybrid f = 0.5 0.60, f = 0.1 0.40, f = 0.25 0.12 (non-monotone), T = 2: 0.00, T = 3: 0.00 | **no gain over tuned I11 or ours_none**; hybrids worse |
| **No-diff stack (H-4 mean-vs-variance)** | field MC p3n240 share 0: mean error **+0.85**, sd 2.25, 80.5 % of fields wrong, positive 54.9 % vs negative 25.6 % (one-sided); at share 0.5: mean +0.10, 7.7 % wrong. Walk success without diff: 0/60 at shares 0, 0.01, 0.03 | The error is **one-sided without diff, near zero-mean with diff** (Stage 0: +0.055): the mean story holds for the single-sign stack, the variance story for the registered stack. The registered diff mitigation is what makes the field unbiased |
| **1c.k k x share (p3n240)** | see section 4 | |
Fixes that did **not** help (R6, R5, R10, R12, R9/R11 at the tested power) should not go into Stage 2; R4 + K is the only validated change.

## 4. 1c.k: k x share grid (p3n240, success, n = 50 ours / 24 B1)
| arm | k | share 0 | 0.03 | 0.1 | 0.25 | 0.5 |
|---|---|---|---|---|---|---|
| ours M0 | 2 | 0.00 | 0.00 | 0.00 | 0.00 | 0.46 [0.33, 0.60] |
| ours M0 | 3 | 0.00 | 0.00 | 0.00 | 0.00 | 0.58 [0.44, 0.71] |
| B1 wv+cal | 2 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| B1 wv+cal | 3 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| B1 bit-sliced (wv+diff+cal+bin) | 2 | 0.00 | 0.00 | 0.00 | 0.04 | 0.58 [0.39, 0.76] |
| B1 bit-sliced | 3 | 0.00 | 0.00 | 0.00 | 0.00 | 0.58 [0.39, 0.76] |
| B1 bit-sliced | 1 | 0.00 | | 0.44 | 0.47 (share 0.2) | 0.50 [0.34, 0.66] |
- At k = 2 and 3 the critical share for ours lies between 0.25 and 0.5 (0 at 0.25), as H8 reported; the registered k = 1 cliff at about 0.03 is not representative of larger variation.
- **B1 native wv+cal collapses at every k >= 2 and share <= 0.5; B1 bit-sliced behaves like ours** (0.58 at share 0.5 for k = 2 and 3; ~0.44-0.50 at k = 1 from share 0.1; cliff between 0 and 0.1 as for ours). So the Stage 0 reading "ours is about 10x less exposed than B1" was an artefact of comparing against B1's native-cell wv+cal stack; with the bit-sliced stack the two machines have the same C2C-share exposure at k = 1-3 in this test. The H8 statement "ours tolerates more variation than B1" is therefore conditional on B1's mitigation choice; the bit-sliced B1 arm is more expensive (bit planes: area/energy not priced here).
- All of this is conditional on the unmeasured C2C share.

## 5. Selected stack re-check at nominal (1e, share 0.5, n = 18; gk n = 15)
p3n480: ours (c = 0.04, K = 0.5n, tiled) 0.78 [0.55, 0.91] vs B3 (selected) 0.83 [0.61, 0.94] vs B1 (ours_none selection, native wv+cal) 0.11 [0.03, 0.33]. gk: ours 1.00, B3 1.00, B1 1.00 (mean cut -6623 / -6638 / -6637). Ours at nominal = ours ideal (0.78 vs 0.75).
**Reading:** after equal tuning, at p3n480 ours reaches success parity with tuned B3 (H8: 0.16 vs 0.48 untuned for ours); at p3n960 B3 still leads (0.39 [0.20, 0.61] with its best configs vs ours 0.17 [0.06, 0.39]; kc2c 0.11; ours_none 0.00), the A3 "greedy ceiling" at near-threshold p3 at 960 is not removed by a better kick; on gk every annealer, tuned or not, already succeeds, and tuned I11 matches them in success but not in mean cut (-6623 vs -6633 / -6638).

## 6. Caveats (must travel with every number above)
1. **`gk` is G43-47: tuning-only.** These graphs were used in P4.02 calibration; success saturates at 1.00 for every annealer and for tuned I11 (the 0.99 x BKS target is easy at 150 sweeps on these graphs), so gk cannot discriminate between arms; the +0.73 gate difference is "recovering annealer-level success from a badly tuned kick (L = 10)". The gate's gk branch also selects the winner and compares it with the reference on the same 15 runs (winner's curse). It is a pass by the registered rule, not strong evidence. No gk result is confirmatory; no fresh Max-Cut instance family exists yet (the rudy generator is not built).
2. **Extra reference row for ours.** In round 2 ours ran 5 rows (top 4 + the registered L = 10 reference, 18 runs each) while every baseline ran 4. The reference is not selectable (excluded from the ranking) and serves only the gate; baselines have no equivalent reference row, so gate differences for ours are measured against its own registered configuration, not against a baseline.
3. **Grid effectiveness.** `pct_lo` has no effect on B3 or ours_none/B1 in the current code (pct_lo 5 vs 10: 96/96 and 90/90 identical runs), so those arms had 6 distinct configs, not 12; ours had 9 distinct labels at p3n480 (aliases at equal L) and 12 on gk; kc2c 12. The nominal "equal count" held, the effective one did not (to the baselines' disadvantage for B3 and none). Several winners sit at a grid edge (ours K = 0.5n; B3 pct_hi 90, knob 0.5): the optimum may lie outside the grid, for every arm.
4. **p4n480 and p4n960 were not tuned** (cost): p4 uses the transferred configs; p4 results in Stage 2 therefore test transfer.
5. Small n (16-18 runs per cell, 5-12 instances): CIs about +-0.2; differences below about 0.3 are not resolved. 1e used 6 instances x 3 seeds.
6. Stage 1 is ideal-device success for tuning (1a), plus targeted nominal tests; no energy or area was computed. Larger L, shorter K and tabu/targeting change restart frequency and kick energy; the priced effect on ETS is unknown until Stage 2.
7. 1c n480 numbers use the registered M0 (L = 10, K = 2n) whose ideal success is only about 0.25 at p3n480, so share-0.03 successes of 0.06 are roughly a quarter of ideal; with 18 runs no variance-reduction fix is distinguishable.
8. M0 k = 3 (0.58) above k = 2 (0.46) is within noise (n = 50).

## 7. Stage 2 gate and recommendation
Formal outcome: PASS via gk (saturated, tuning-only, winner scored on its own selection runs); **substantive outcome: FAIL** at p3n960 (+0.17, Newcombe lower bound -0.04; the 3/18 is also a winner-of-top-4 estimate, biased upward). **Stage 2 is not licensed by the gate**; it can only go ahead as a narrower, explicit author decision (confirm the one validated change, R4 + K, at 480 spins, with energy as the primary question). Substantive reading: R4 + K is a validated improvement (colouring at 480, gk), R6/R5/R10/R12/R9/R11 are not; p3n960 does not pass its own criterion and B3 stays ahead there. The Stage 2 DRAFT (`prereg/hw/S2_confirmatory_DRAFT.md`, not frozen) was rewritten after review review as a **480-only scope with energy (ETS) as the primary question**; 960 and Max-Cut are stated limitations (Stage 1: B3 ahead at 960; Max-Cut has no fresh instances). See `STAGE1B_RETUNE.md` for the re-tuned equal-effort grids and the first ETS numbers.
