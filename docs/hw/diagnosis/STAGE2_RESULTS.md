# Stage 2 results: confirmatory energy test of the retuned stack at 480 spins

Prereg `prereg/hw/S2_confirmatory.md` (FROZEN at `86a4fce` before any Stage 2 record; bundle pin `a02aa80`; `evaluate_s2.py` is unchanged between the pin and the freeze, which differ only in documents).
Return `00_admin/s2_return/20261122T042005Z_stage2` (checksums verified): 263 of 263 jobs done, 0 failed, 16 vCPU, 98 min of scheduled work (02:42-04:20 UTC), R13 gate `0.5.r13_480` passed (tiled-256 nominal identical to ideal for both records, best_E 2 / 1, 124 800 / 77 760 flips identical).
**Reproduction:** the registered evaluator was re-run locally on the unpacked records with its registered settings (`evaluate_s2.py --records ... --out ...`, B = 10 000): **the text of the report and the JSON are byte-identical to the cloud report** (`s2_evidence/`).
Everything in sections 1-3 is the registered analysis. Section 5 is exploratory and labelled as such. All numbers: stand-in device models (ratios only, about x2), the unmeasured C2C share (nominal = share 0.5 at k = 1), tag-11 fresh planted instances (keys 2301.. / 2401.., 64 instances x 3 seeds per primary cell).

## 1. Registered decision (dual-B3 rule, evaluated at p3n480, primary pricing = corrected B-1, B-2, B-3)
**NO ENERGY ADVANTAGE SHOWN.** Against B3_sel ours_new / B3_sel = 1.48 [0.97, 2.12], against B3_h8 1.23 [0.84, 1.69]: both inconclusive (neither a win, so "supported" fails; neither a loss under the evaluator's loss class, so "falsified" fails). As pre-declared, this is read as **no energy advantage shown, not as parity**.
**Pricing sensitivity (pre-declared, reported next to the verdict):** under the frozen H8 pricing the same rule gives **FALSIFIED**: ours_new / B3_sel = 1.64 [1.08, 2.37], a loss (success difference +0.21), B3_h8 1.37 [0.94, 1.88] inconclusive. So the primary decision is "no advantage shown", and the energy hypothesis does not survive the more adverse (frozen) pricing.

## 2. Primary contrasts (nominal; Holm m = 6; ETS99 ratio ours_new / comparator, < 1 favours ours)
| cell | comparator | ETS ratio [95 % CI] | d success [95 % CI] | Holm p | verdict (primary pricing) | verdict (frozen pricing) |
|---|---|---|---|---|---|---|
| p3n480 | B3_sel | 1.48 [0.97, 2.12] | +0.21 [+0.09, +0.33] | 1 | inconclusive | **loss** (1.64 [1.08, 2.37]) |
| p3n480 | B3_h8 | 1.23 [0.84, 1.69] | +0.00 [-0.12, +0.11] | 1 | inconclusive | inconclusive (1.37 [0.94, 1.88]) |
| p3n480 | B1_sel | 0.078 [0.024, 0.145] | +0.52 [+0.41, +0.62] | 0.0006 | **win** | win (0.075) |
| p4n480 | B3_sel | 1.11 [0.75, 1.48] | +0.02 [-0.09, +0.12] | 1 | inconclusive | inconclusive (1.23 [0.83, 1.64]) |
| p4n480 | B3_h8 | 0 [0, 0] | +0.73 [+0.64, +0.82] | 0.0006 | "win" (see note) | "win" |
| p4n480 | B1_sel | 0.131 [0.073, 0.182] | +0.52 [+0.42, +0.62] | 0.0006 | **win** | win (0.124) |
Note on p4n480 vs B3_h8: B3_h8 (the H8-registered configuration, transferred) never reaches the target on p4n480 (0 of 192 runs), so its ETS is infinite and the ratio is 0. The evaluator labels this "win"; the H8 convention would call it "not evaluable (success win)". It is a success difference of +0.73, not an energy result, and p4n480 does not enter the decision.
**Success rates (192 runs per cell, Wilson 95 %):**
| arm | p3n480 | p4n480 |
|---|---|---|
| ours_new (L = 10, K = 0.25n; ideal = nominal) | 0.57 [0.50, 0.64] | 0.73 [0.66, 0.79] |
| B3_sel | 0.36 [0.30, 0.43] | 0.71 [0.65, 0.77] |
| B3_h8 | 0.57 [0.50, 0.64] | 0.00 [0.00, 0.02] |
| B1_sel (native, wv+cal) | 0.06 [0.03, 0.10] | 0.21 [0.16, 0.27] |
| ours_h8 (L = 10, K = 2n; bridge) | 0.14 [0.10, 0.20] | 0.28 [0.22, 0.35] |
Energy per run (nominal for ours and B1, digital for B3, fJ): ours_new 8.1e11 (p3n480) / 8.4e11 (p4n480), B3_sel 5.3e11 / 5.5e11, B3_h8 5.7e11, B1_sel 1.0e12 / 1.1e12. Ours spends 1.4-1.5x more energy per run than B3, of which the nominal mitigation accounts for +13 % (ideal 7.2e11); success parity (B3_h8) or an advantage (B3_sel) therefore translates into ETS ratios of 1.2-1.5.
Reading: the retune achieved what it was tuned for (success parity with, or above, tuned B3 at p3n480; far above the H8 configuration and above B1), but **not** an energy advantage: the registered energy hypothesis is not supported.

## 3. Report-only cells (pre-registered as report-only; not part of the decision)
| contrast | instances x seeds | ETS ratio [95 % CI] | d success [95 % CI] |
|---|---|---|---|
| **Bridge (S2-B)** p3n480 nominal: ours_new vs ours_h8 | 64 x 3 | 0.158 [0.090, 0.401] | +0.43 [+0.32, +0.54] |
| p4n480 nominal: ours_new vs ours_h8 | 64 x 3 | 0.21 [0.13, 0.32] | +0.45 [+0.34, +0.56] |
| p3n240 / p4n240 nominal: ours_new vs ours_h8 | 16 x 3 | 0.447 [0.164, 1.02] / 0.563 [0.279, 1.11] | +0.27 [+0.10, +0.46] / +0.15 [-0.04, +0.33] |
| **No-regression (S2-D)** p3n240: ours_new vs B3_sel / B3_h8 / B1_sel | 16 x 3 | 0.56 [0.21, 0.90] / 0.50 [0.23, 0.80] / 0.125 [0.045, 0.192] | +0.40 / +0.15 [0.00, +0.29] / +0.58 |
| p4n240: ours_new vs B3_sel / B3_h8 / B1_sel | 16 x 3 | 0.81 [0.40, 1.43] / 0 (B3_h8 at 0 %) / 0.18 [0.07, 0.31] | +0.02 / +0.77 / +0.38 |
| p3n480 nominal: ours_new vs B1 bit-sliced (B1_bs) | 64 x 3 | 0.148 [0.074, 0.231] | +0.46 [+0.35, +0.56] |
| ETS-selected sensitivity p3n480: ours_ets (c 0.04, K = 0.125n) vs B3_ets | 64 x 3 | 1.06 [0.49, 1.67] | +0.52 [+0.42, +0.62] |
Notes: at 240 spins ours_new is not worse than H8 or B3 (success 0.96 on p3n240) and its ETS ratios against B3 are below 1 with intervals that exclude 1 at p3n240 (n = 16, report-only, not Holm-adjusted); the retune did not regress the small cells. B1_bs (bit-sliced) reaches only 0.11 success at p3n480, so the bit-sliced B1 is not stronger here. The ETS-selected pair is not an operating point anyone would use (B3_ets success 0.08).

## 4. Deviations from the frozen prereg
None in the protocol (263/263 jobs, the planned arms, instances, seeds, pricing and gate). Items to note:
1. The evaluator's "win" label for a comparator at 0 % success (p4n480 vs B3_h8, p4n240 vs B3_h8) differs from the H8 convention "not evaluable"; the prereg says the evaluator governs wording. It does not touch the decision.
2. Wall time was 98 min against 132 min simulated; cost below the Rs 133 worst case (set-up, gate and collection also within caps; exact Rs from the cloud bill).
3. The Stage 1b statement "restart block share 0.09 % of ours' energy" used the energy blocks stored in the records (frozen cost table). Under `measured_v2` the restart block is about 8 % of ours' energy for **both** ours_new and ours_h8 (it is the restart unit's own cost, not proportional to kicks), so that share is not evidence about kick energy; the direct measure is in section 5.

## 5. Exploratory looks (NOT confirmatory; not pre-registered analyses)
1. **Kick energy.** ours_new makes about five times more restarts than ours_h8 (K = 0.25n vs 2n) and spends 7.19e11 vs 7.08e11 fJ per run at p3n480 ideal: **+1.6 %** energy per run. The kick is not what makes ours more expensive than B3; the gap is the analog array/ADC energy per step (and the mitigation), about 1.4-1.5x B3's per-run energy.
2. **Tuning-to-confirmation shrinkage.** Success on the tuning instances (p3n480, 24 runs) versus the fresh instances (192 runs): ours 0.83 -> 0.57; B3_sel 0.71 -> 0.36; B3_h8 0.79 -> 0.57; ours_h8 0.21 -> 0.14. Every selected configuration fell (winner's curse plus the tuning instances being easier); the ranking ours >= B3_sel and ours = B3_h8 survived, and the gap to B3_sel (+0.21) is larger than at tuning (+0.12).
3. **Pricing dependence.** The decision-relevant contrast (p3n480 vs B3_sel) moves from inconclusive to a loss when the corrected pricing (B-1..B-3, net effect favouring ours) is replaced by the frozen H8 pricing; the claim "no loss to B3" is therefore pricing-fragile. This is a statement about the pre-declared sensitivity, not a new analysis.
4. **Context against H8 (different instances and configurations, not comparable as a test):** at p3n480 the H8 ratio ours/B3 was 5.4 (frozen) / 4.8 (corrected); the retuned stack is at 1.2-1.5. The retune closes most of the gap; it does not reverse it.

## 6. Plain-language summary
We retuned our machine's restart rule (a shorter "give up and kick" window; the kick itself stays 10 spins) with the same tuning effort as the baselines and then tested it on fresh 480-spin colouring problems. **On success it works:** at 3-colouring it now solves 57 % of runs, level with the tuned digital annealer B3 (57 %) and well above B3's other tuning (36 %), up from 14 % with the old setting; it also beats the B1 design (6-21 %) in energy by roughly 8 to 13 times. **On energy it does not win:** our machine spends about 1.4-1.5 times as much energy per run as B3, so even at equal success its energy-to-solution is 1.2-1.5 times B3's. With the registered pricing this is statistically unresolved (intervals include 1), which we read as "no energy advantage shown", not as a tie; with the older, harsher pricing it is a clear loss to one of the two B3 settings. The restart kicks themselves cost almost nothing (+1.6 % energy per run), so the remaining gap is the analog array and converters. What this does not cover: 960-spin problems (B3 was ahead in the pilot), Max-Cut (no fresh instances; H8's Max-Cut loss stands), and any real device (the C2C-variation share is unmeasured, models are stand-ins).
