# Stage 3.2 results: confirmatory energy and success test of the round-2 stack (fresh instances, tag 12)

Prereg `prereg/hw/S3_confirmatory.md` (FROZEN at `fd87994` before any 3.2 record; bundle pin `863e54d`; `evaluate_s3.py` and the job list are unchanged between the pin and the freeze, which differ only in documents). Return `00_admin/s32_return/20261122T195208Z_stage2` (the folder carries the collect label "stage2"; it is Stage 3.2; checksums verified): **200 of 200 jobs done, 0 failed**, R13 gate `0.5.r13_960` passed (fresh tag-12 spec, tiled-256 nominal identical to ideal for both records, best_E 6 / 6, 576 000 / 568 320 flips identical), 16 vCPU, 71 min of scheduled work (18:41-19:52 UTC; 176 min simulated).
**Reproduction:** the registered evaluator was re-run locally on the unpacked records with its registered settings (`evaluate_s3.py --records ... --out ...`, B = 10 000 for the primary): **report text and JSON are byte-identical to the cloud report** (`s3_2_evidence/`).
Sections 1-4 are the registered analysis. Section 5 is a supplementary computation made after the registered run (the registered evaluator does not output the pre-declared report-only contrasts); sections 6-7 are exploratory looks, labelled. All numbers: stand-in device models (ratios only), unmeasured C2C share (nominal = share 0.5, k = 1), tuned configurations of Stage 3.1 (`STAGE3_1_RESULTS.md`).

## 1. Registered decisions per cell (dual-B3 rule, Holm m = 8, margin -0.10; a comparator at 0 % success drops out of the rule; "supported" also needs the verdict at hardware estimates x2)
| cell | decision | note |
|---|---|---|
| **p3n480** | **NO ENERGY ADVANTAGE SHOWN** | win against B3_sel, inconclusive against B3_h8 (see 2) |
| **p4n480** | **SUPPORTED** (also at hardware estimates x2: yes) | win against B3_sel; B3_h8 is at 0 % success and drops out, so the decision rests on B3_sel alone |
| **p3n960** | **NO ENERGY ADVANTAGE SHOWN** | both contrasts inconclusive (frozen pricing: FALSIFIED) |
| **Max-Cut** | **FALSIFIED** | loss to both B3 comparators |

## 2. Primary contrasts (nominal; ETS99 ratio ours_stack / comparator, < 1 favours ours; 64 x 3 at 480, 64 x 2 at 960, 20 x 5 Max-Cut)
| cell | comparator | ETS ratio [95 % CI] | d success [95 % CI] | Holm p | verdict |
|---|---|---|---|---|---|
| p3n480 | B3_sel | 0.50 [0.32, 0.65] | +0.29 [+0.19, +0.40] | 0.0008 | **win** |
| p3n480 | B3_h8 | 0.54 [0.35, 0.70] | +0.01 [-0.104, +0.12] | 0.0008 | inconclusive |
| p4n480 | B3_sel | 0.43 [0.28, 0.58] | +0.09 [-0.01, +0.20] | 0.0008 | **win** |
| p4n480 | B3_h8 | 0 [0, 0] | +0.71 [+0.61, +0.80] | 0.0008 | not evaluable (B3_h8 at 0 / 192) |
| p3n960 | B3_sel | 1.22 [0.60, 2.5] | +0.02 [-0.09, +0.13] | 1 | inconclusive |
| p3n960 | B3_h8 | 1.49 [0.87, 2.7] | -0.20 [-0.33, -0.08] | 1 | inconclusive |
| Max-Cut | B3_sel | 13.2 [7.6, 20.6] | -0.30 [-0.43, -0.18] | 1 | **loss** |
| Max-Cut | B3_h8 | 9.1 [5.6, 13] | -0.30 [-0.43, -0.18] | 1 | **loss** |
**The p3n480 decision is a knife-edge on the success margin, not on energy:** the ETS ratio against B3_h8 (0.54) has an interval entirely below 1, but the success-difference lower bound (-0.1042) is just below the registered -0.10 margin, so the rule gives "inconclusive" and the cell decision is "no energy advantage shown". Under the registered rule that is the outcome; it is not a statement that ours is not cheaper (its ETS is half of both B3 comparators').
**Success rates (Wilson 95 %-level counts as in the report; nominal for ours, ideal for B3):** p3n480 ours 0.66, B3_sel 0.36, B3_h8 0.65; p4n480 ours 0.71, B3_sel 0.61, B3_h8 0.00; p3n960 ours 0.20, B3_sel 0.17, B3_h8 0.40; Max-Cut (0.99 x reference) ours 0.70, both B3 1.00. Energy per run (fJ): ours 3.06e11 / 3.05e11 / 2.77e12 / 7.24e11 against B3_sel 4.38e11 / 4.65e11 / 4.02e12 / 1.12e12 (p3n480 / p4n480 / p3n960 / Max-Cut): ours spends about 0.65-0.70x B3's energy per run in every cell, which is the T-1 + T-5 + T-6 effect.

## 3. Pre-declared sensitivities (every one re-prices and re-bootstraps; decisions per cell p3n480 / p4n480 / p3n960 / Max-Cut)
| sensitivity | p3n480 vs B3_sel / B3_h8 | p4n480 vs B3_sel | decisions |
|---|---|---|---|
| **hardware estimates x2 (registered condition)** | 0.53 win / 0.57 inconclusive | 0.45 win | no adv. / **supported** / no adv. / falsified |
| hardware estimates x0.5 | 0.49 / 0.52 | 0.42 | same as nominal |
| **margin -1 pp** | 0.50 win / 0.54 inconclusive | 0.43, **inconclusive** (success lower bound -0.0104) | p4n480 becomes "no advantage shown" |
| **frozen H8 pricing** | 1.24 / 1.33 inconclusive | 1.12 inconclusive | p3n960 becomes **falsified** (3.7 / 4.5 losses); p4n480 no advantage |
| B3 un-gated (favourable to ours) | 0.42 win / 0.45 | 0.36 win | as nominal |
| correction table 4 | 0.58 win / 0.62 | 0.50 win | p3n960 falsified (B3_h8 loss 1.75) |
| **correction table 16** | 0.82 / 0.88 inconclusive | 0.70 inconclusive | p4n480 not supported; p3n960 falsified |
| screening double-counted | 0.50 / 0.54 | 0.43 win | as nominal |
| Max-Cut target 0.995 | unchanged | unchanged | Max-Cut falsified (ratios 21-24, ours success 0.14 vs 0.63 / 0.91) |
| Max-Cut reference raised post hoc | unchanged | unchanged | Max-Cut falsified (13.3 / 9.2) |
Note (internal review s18): "frozen H8 pricing" also removes every architecture credit (t1f, t5, t6, b3b), so it prices the incremental-field machine as the old full-read machine; it measures dependence on the T-1 / T-5 / T-6 hardware estimates, not only on the B-1..B-3 corrections.
Reading: the p4n480 "supported" is **fragile to three pre-declared sensitivities** (margin -1 pp, frozen pricing, correction table 16) and it relies on B3_sel alone because B3_h8 (transferred) scores 0 / 192 on p4n480. The ETS advantage at p3n480 is robust to every sensitivity except frozen pricing and table 16.

## 4. p3n960 and Max-Cut (the two cells where ours does not win)
- **p3n960 (64 x 2):** ours 0.20 vs B3_sel 0.17 vs B3_h8 0.40 (success -0.20 [-0.33, -0.08] against B3_h8); ETS ratios 1.22 / 1.49 with intervals that include 1: no advantage shown. The architecture's lower energy per run (0.69x) is offset by lower success against B3_h8. Under frozen pricing both contrasts are losses. The tuning-set tie at 960 (0.33 each) did not survive: ours 0.33 -> 0.20, B3_sel 0.33 -> 0.17, B3_h8 0.33 -> 0.40.
- **Max-Cut (MC-1, fresh random 1000-node graphs, reference = best of 8 x 4000-sweep SA):** ours_stack reaches 0.99 x reference in 70 % of runs against 100 % for both B3 comparators (0.995: 14 % against 63 % / 91 %; mean cut / reference 0.9916 against 0.9956 / 0.9969); the ETS ratio is 9-13 (loss), 21-24 at the 0.995 target. This is a **falsification of the energy hypothesis on this cell** and consistent with H8 (the Max-Cut loss stands). Caveat: ours' configuration (K 0.25n, esc A) was tuned on colouring only (global rule) and was not tuned for Max-Cut; Stage 3.0 found no algorithm hook with a Max-Cut signal, so a Max-Cut-specific tuning is untested rather than ruled out.

## 5. Report-only contrasts (supplementary: computed after the registered run by `scripts/testing/s32_reportonly.py`, same pricing; outside the Holm family; exploratory)
| contrast (p3n480, nominal, 64 x 3) | ETS ratio ours_stack / comparator [95 % CI] | d success |
|---|---|---|
| vs ours_new (Stage 2 configuration, standard pricing): what the architecture + esc A add | 0.36 [0.27, 0.47] | -0.01 [-0.11, +0.08] |
| vs B1_sel (native wv+cal; Stage 2 comparator) | 0.042 [0.019, 0.065] | +0.56 [+0.45, +0.65] |
Against B1 the stack wins by about 24x in ETS (success 0.66 vs 0.10). Against the Stage 2 configuration the energy gain is about 2.8x with no change in success (esc A added nothing at p3n480: 0.66 vs 0.67), i.e. the gain is the architecture pricing, not the algorithm.

## 6. Deviations
1. **Launch caps:** the run used the reviewed launch environment (deadline 240 / hard 255 min, worst case Rs 161, set in internal review s17) instead of the draft's 200 / 215 (Rs 140); the run needed 71 min, so the caps never bound. No protocol deviation otherwise (200/200 jobs, planned arms, instances, seeds, pricing, gate).
2. The registered evaluator reports success and energy per run for the primary arms only; the pre-declared report-only contrasts (bridge, B1) are in the supplementary script of section 5.
3. The evaluator's "win" rule on p3n480 vs B3_h8 sits on the -0.10 margin to within 0.004 (see section 2); no analysis was changed.

## 7. Exploratory looks (not registered)
1. **Tuning-to-fresh shrinkage again:** ours 0.79 / 0.88 / 0.33 (tuning p3n480 / p4n480 / p3n960) -> 0.66 / 0.71 / 0.20; B3_sel 0.62 / 0.83 / 0.33 -> 0.36 / 0.61 / 0.17; B3_h8 0.79 / 0.00 / 0.33 -> 0.65 / 0.00 / 0.40. Every tuned configuration fell except B3_h8 at 960; the ranking at 480 survived.
2. **Where the energy advantage comes from:** energy per run is about 0.65-0.70x B3's in every cell, constant across problem classes; the success rates then decide the ETS ratio (advantage where ours' success is at least comparable, loss where it is clearly lower: Max-Cut, p3n960 vs B3_h8).
3. **Pricing dependence:** under the frozen H8 pricing the p3n480 / p4n480 ETS advantage disappears (1.12-1.33) and 960 becomes a loss: the energy result depends on the T-1 / T-5 / T-6 hardware being built as priced (estimated, not synthesised); table 16 removes the p4n480 support.

## 8. Plain-language summary
On fresh 480-spin colouring problems, our machine with the exact incremental-field design (priced as an estimated hardware stack) spends **about half the energy per solution** of the tuned digital annealer B3: 0.50 against the tuned-by-selection B3 and 0.54 against the original B3 setting at 3-colouring, 0.43 at 4-colouring. By the pre-registered rules this is **supported at 4-colouring (480 spins)**, including when the hardware estimates are doubled, but only against one of the two B3 settings (the other scores 0 % at 4-colouring), and it does not survive three of the pre-declared stress tests (a stricter success margin, the older pricing, or a larger correction table). At 3-colouring the energy ratio is just as good, but the registered success rule leaves it "no energy advantage shown" by a hair (the success difference lower bound is -0.104 against a -0.10 limit). **At 960 spins there is no advantage** (success is not better and energy ratios are 1.2-1.5 with intervals around 1; with the older pricing it is a loss), and **on Max-Cut the hypothesis is falsified**: our machine reaches the target in 70 % of runs against 100 % for B3 and costs 9-13 times more energy to solution. Against the FeFET design B1 it wins by about 24 times. All of this is conditional on stand-in device models, the unmeasured device variation, and on the incremental-field hardware (T-1, T-5, T-6, screening) being built as estimated.

## Erratum (2026-11-23): T-5 in the registered pricing
The registered primary pricing (`evaluate_s3.py:32`, `all,b3b,t1f,t5,t6`) includes T-5, the read/select overlap. Round 3 found it causally unbuildable: the update read needs the spin chosen by the same step's selection (`the round-3 design notes.md` §2.2; `the engineering notes.md` §14.1).
Re-priced without T-5 (EXPLORATORY): p4n480 0.53 (measured_v3) / 0.65 (measured_v4 candidate), still SUPPORTED by the rule; p3n480 no advantage shown (0.61 / 0.75); p3n960 **FALSIFIED** (1.50-1.84 / 1.78-2.18); Max-Cut FALSIFIED.
Under measured_v4, p4n480 is lost with analog x2, B3 SRAM x0.5, B3 RNG x0.5, or full gating on both machines.
The registered p4n480 "supported" must be cited only with this caveat. Details and the side-by-side table: `prereg/hw/S3_confirmatory_amendment1.md`. The registered sections above are unchanged.

