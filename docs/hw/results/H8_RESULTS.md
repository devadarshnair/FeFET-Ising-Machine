# H8 full study: CORE tier results

Prereg `prereg/hw/H8_full.md`, frozen at `237fe1e` before any H8 data (not edited here). Design and review history are in `H8_DESIGN.md`.
Cloud return `00_admin/h8_return/20261121T010938Z_core/` (16-vCPU profile, checksums verified). The scheduler ran 487 of 487 jobs with rc 0 and none failed.
Evaluator: `scripts/testing/evaluate_h8.py --tier core`. Full generated tables are in `h8_eval/h8_report_core.md` and `.json`.

All numbers are from stand-in BSIM4 / FreePDK45 models. Only the ratios are meaningful, and absolute energies carry about x2 uncertainty.
Every variation statement is conditional on the unmeasured C2C share (>= 0.25 for ours, >= 0.5 for B1).

## 0. Integrity checks
- **Rerun vs cloud report:** the local rerun (`evaluate_h8.py --raw sim/out/hw/h8 --tier core`) is byte-identical to the cloud `h8_report_core.json` and `.md` (json sha256 68f3fdecc7b98292..., md e94b0ddfd7699fab...).
- 486 of 486 raw files were read, with no unread files. The global Holm family is complete (20 of 20). The `ours.kc2c` arm is present.
  The cost-table sha256 is `623544a8...`.
- Every planned job has its output. The record count equals the planned (instance, seed) count in every job, for 21 680 records in total.
- Every record carries git head `237fe1e` with a clean tree. Every record has the fresh tag 9, with inst_index 500 to 554.
- No record has a NaN or missing `best_E`, zero steps or flips, or a non-finite or non-positive priced energy. No job timed out. The longest job ran 28 min.
  The checks are in `h8_eval/sanity.json`.

## 1. H8-A primary verdicts (nominal condition, each machine with its chosen mitigation, global Holm m = 20)
Each machine runs its chosen mitigation: ours uses wv + diff + cal, and B1 uses wv + cal. B3 is digital, so its nominal and ideal numbers are the same.
The ETS99 ratio is ours_kc2_i11 divided by the comparator, so a value below 1 favours ours. The ideal-device verdict (per-cell Holm, secondary) is shown alongside, as section 7 of the prereg requires.

| family cell | vs B3_v2: ratio [CI], p_glob | verdict nominal / ideal | vs B1_best: ratio [CI], p_glob | verdict nominal / ideal | sensitivity flags |
|---|---|---|---|---|---|
| p3n120 | 0.61 [0.36, 0.97], 0.155 | inconclusive / inconclusive | 0.23 [0.14, 0.33], 0.002 | **win** / win | none |
| p3n240 | 2.58 [1.54, 3.57], 1.0 | **loss** / loss | 0.55 [0.32, 0.75], 0.003 | inconclusive (success CI crosses -1 pp) / inconclusive | vs B3: canonical table gives inconclusive |
| p3n480 | 5.41 [2.46, 13.4], 1.0 | **loss** / loss | 0.75 [0.26, 1.68], 1.0 | inconclusive / inconclusive | none |
| p3n960 | inf (ours 0 %, B3 45 %) | not evaluable / not evaluable | both 0 % | not evaluable / not evaluable | none |
| p4n120 | 0.010 [0.004, 0.018], 0.002 | **win** / win | 0.006 [0.002, 0.010], 0.002 | **win** / win | none |
| p4n240 | B3 0 %, ours 67 % | not evaluable (success win) / same | B1 0 %, ours 67 % | not evaluable (success win) / ideal win 0.002 | none |
| p4n480 | B3 0 %, ours 18 % | not evaluable (success win) / same | 0.11 [0.00, 0.36], 0.006 | **win** / win | none |
| p4n960 | both near 0 (ours 5 %) | not evaluable / not evaluable | same | not evaluable / not evaluable | none |
| DIMACS-style (282 spins) | 0.007 [0.000, 0.017], 0.002 | **win** / win | 0.002 [0.000, 0.006], 0.002 | **win** / win | none |
| Max-Cut G51-54 (1000) | 18.8 [9.6, 44.6], 1.0 | **loss** / loss | 2.85 [1.14, 7.69], 1.0 | **loss** / loss | vs B1: canonical table gives inconclusive |

Tally of the 20 primary verdicts: 6 win, 4 loss, 3 inconclusive and 7 not evaluable.
The six wins are DIMACS x2, p4n120 x2, p3n120 vs B1 and p4n480 vs B1. No sensitivity flips a win.
Three of the 7 not-evaluable cells are cases where ours succeeds and the comparator never does: p4n240 vs both machines (67 % vs 0 %) and p4n480 vs B3.
These are quality wins on success, but under the registered rule they are not energy verdicts.

### Secondary contrasts (per-cell Holm)
- **ours_none vs B3_v2:** loss or not evaluable in every cell except p4n120, which is inconclusive. Without I11 our machine is about 2.4 to 6.6x worse than B3 in energy.
- **ours.kc2c vs B3_v2:** this is the fairness arm (Kc2 with B3's T_final knob). It loses to B3 (2.5 to 11x) wherever both machines succeed, and is inconclusive on p4n120.
- **ours_kc2_i11 vs ours.kc2c:** win on DIMACS and p3n120 / p4n120 (0.005 to 0.23). It is inconclusive on p3n240 / p3n480 / p4n480 / p4n960 and a loss on Max-Cut (6.2x).
  So the advantage comes from I11, not from the annealing schedule.
- **Max-Cut:** ours_none, ours.kc2c, B1 and B3 all reach 96 to 100 % success. ours_kc2_i11 reaches only 58 % nominal and 42 % ideal.
  On Max-Cut, I11 hurts.

## 2. Pricing sensitivities (`measured_v2` primary; six sensitivities)
The six sensitivities are: canonical table, baselines on the lane-path clock, ungated generators, worst N = 1024 clock, 20 ns analog settle, and no one-time mitigation energy.
Two primary verdicts flip, both under the canonical table and both from loss to inconclusive:
- Max-Cut, ours vs B1;
- p3n240, ours vs B3.

No win flips under any sensitivity, and no other sensitivity changes any verdict. The 20 ns analog-settle and no-once-cost readings leave all 20 verdicts unchanged.

## 3. Mitigation tax (H8-C), ETS99 of nominal over ideal
- **ours_kc2_i11:** x1.10 to 1.21 (DIMACS 1.21, p3n120 1.15, p4n120 1.12, p3n240 1.10, p4n240 1.11), with no success cost. On Max-Cut, success is 0.42 ideal and 0.58 nominal.
- **B1_best:** x1.01 to 1.81, with a small success loss on p4 (0.08 to 0.07 at 120 spins, 0.06 to 0.03 at 480 spins).
- The mitigation area cost is larger than the energy cost: +13 to 38 % for both ours and B1, growing with N. This is the cause of the area "loss" vs B3 in several nominal cells.

## 4. Ablation ladder with mitigations (H8-D; p3n240 / p4n240 ideal and nominal, G1000 nominal)
- The DA, MESA and Kc2 rungs (without I11) reach 0 % success in every ladder cell. They are worse than L_none, which reaches 48 % on p3n240 and about 100 % on G1000.
- Adding **I11** is the step that matters: +62 to +75 pp over Kc2 in every cell.
- Adding **I7v2** on top of I11 is harmful (-46 to -75 pp). Adding I10 changes nothing measurable, and I5 is 0 % or no better.
- Against `none`, Kc2 + I11 is a success win on p4n240 (+62 pp). It is inconclusive on p3n240 (+20 pp, ratio 0.48) and on G1000 (ratio 3.8, a loss in energy).
- So the registered stack is effectively "I11 on a Kc2 base". The other rungs add nothing.

## 5. Variation stress (H8-E, design point p3n240 / p4n240)
All of this section is conditional on the unmeasured C2C share.
- **ours_kc2_i11:** robust to k up to 3 at C2C share 0.5 (p3 0.57 to 0.70, p4 0.58 to 0.70) and to drift 0.01. It collapses unmitigated (0 %) and at C2C share 0 (2 to 7 %).
  At k = 2 it also needs a C2C share of at least 0.5 (0.25 gives 0 to 7 %). Drift 0.02 kills p3 (0 %) but not p4 (62 %). Drift 0.05 kills both.
- **B1_best on p3n240:** collapses at C2C share 0.25 or below even at k = 1, at k >= 1.5, at drift >= 0.02 and unmitigated.
  It survives k = 3 only with the heavier wv + diff + cal + bin stack (45 %). On p4n240 the B1 stress is uninformative because ideal B1 success is only 2 %.
- **Net:** under the same assumptions, ours tolerates more variation than B1. Both machines depend on the C2C assumption, and ours depends on it more sharply at share 0.
  The "restored" flag is False on several rows with a 0.00 difference only because n = 60 makes the Newcombe lower bound fall below -0.10.

## 6. Scale (H8-B), success at 120 -> 240 -> 480 -> 960 spins (nominal)
| machine | p3 | p4 | largest N at success >= 0.5 / 0.1 (p3; p4) | log-log ETS slope p3 / p4 |
|---|---|---|---|---|
| ours_kc2_i11 | 0.97, 0.58, 0.16, 0.00 | 0.99, 0.67, 0.18, 0.05 | 240 / 480; 240 / 480 | 5.4 (3 pts) / 5.3 |
| B3_v2 | 0.96, 0.85, 0.48, 0.45 | 0.07, 0, 0, 0 | 240 / 960; none | 3.7 / n/a |
| B1_best | 0.86, 0.49, 0.13, 0.00 | 0.07, 0, 0.03, 0 | 120 / 480; none | 4.5 / n/a |
| ours_none | 0.87, 0.49, 0.12, 0.00 | 0.08, 0, 0.06, 0 | 120 / 480; none | 4.5 / 3.0 |

**How the energy advantage changes with size.** On p3 our ETS ratio vs B3 goes 0.61 -> 2.58 -> 5.41 -> not evaluable, because ours reaches 0 % at 960 while B3 holds 45 %.
Our ETS grows with slope about 5.4 against 3.7 for B3. Against B1 the ratio rises from 0.23 -> 0.55 -> 0.75 toward 1.
On p4 ours is the only machine above 10 % success at every size up to 480, but at 960 it reaches only 5 %.
Every hardware machine falls apart by 960 spins at the fixed budget. A config tuned on 120 to 240 spins and applied unchanged at larger N is a registered limitation.

## 7. Software context (H8-F; no energy claim)
TabuCol reaches 97 to 100 % success in every colouring cell, and the 20x TabuCol check solves all instances.
DSATUR and SA succeed less often than ours on small instances and fall to near 0 at 480 spins and above. On Max-Cut, SA reaches 25 %.
The software arms are context only. No software energy is estimated.

## 8. Power / MDE (core)
The minimum detectable success difference (MDE) is 0.20 at 120 spins, 0.225 at 240, 0.328 at 480, 0.452 at 960, 0.374 on DIMACS (11 x 8) and 0.615 on G51-54 (4 x 6).
Effects below the MDE are "not resolved", not ties.
The three inconclusive primaries (p3n120 vs B3, p3n240 / p3n480 vs B1) have success differences of 0.01 to 0.09, well under their MDE. The 960 cells resolve only gaps larger than about 45 pp.

## 9. Bottom line
- **Ours wins** (energy, global Holm, robust to every sensitivity) on DIMACS-style graphs against both machines (100x or more) and on small 4-colouring (p4n120) against both machines (about 100x).
  It also wins against B1 on p3n120 (about 4x) and on p4n480 (about 9x).
  On 4-colouring at 240 to 480 spins it is the only hardware machine that solves anything. That is a success win, but under the registered rule it is not an energy verdict.
- **B3 wins** 3-colouring from 240 spins up (2.6x at 240 and 5.4x at 480, then 45 % vs 0 % at 960) and Max-Cut (19x).
  **B1 wins** Max-Cut (2.9x; this becomes inconclusive under the canonical table).
- Because of the Max-Cut losses, the claim "ours is a better Ising machine" is not supported. The supported claim is narrower: ours is better on constrained colouring-type structure where I11 applies, at up to about 480 spins.
- **Conditions:** all baselines are our own implementations, and A1 / A3 / A5 were not reproduced. B2 is excluded, and B1 / B3 were never synthesised (same-tree clock rule).
  Results are under stand-in device models (ratios only). Variation results depend on the C2C share. The analog settle and area sensitivities flip no verdict, and only the canonical table flips two losses to inconclusive.

## 10. Would FULL (+2040 spins, G27-31 2000 nodes, about +Rs 283) add decision-relevant information?
Probably not. At 960 spins every machine except B3 on p3 is already at 0 to 5 %, so the 2040 cells would almost certainly be "not evaluable".
Those cells also have an MDE of 0.75 (4 x 2) and are priced by N > 1024 extrapolation, so they cannot carry a headline verdict.
G2000 would repeat a Max-Cut picture in which ours already loses at 1000.
FULL tightens the MDE at 120 to 960 only modestly (0.20 -> 0.18, 0.45 -> 0.375). The inconclusive cells have effects far below even those MDEs, and the p3n480-vs-B1 ratio CI is [0.26, 1.68].
A better use of the money would be a size-scaled budget or a retune at 480 to 960 spins, but that would need a new prereg.
