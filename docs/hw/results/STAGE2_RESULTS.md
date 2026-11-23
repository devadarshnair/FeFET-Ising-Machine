# Stage 2 results (rented cloud CPU run, 503/503 jobs)

Run pin 6283c1e; preregs H0/H2/H3/H5 frozen at a5f2866 before any scored value was read (16 Nov IST; untagged, a5f2866). Raw returns (checksums verified):
`00_admin/cloud_cpu_return/20261116T160047Z_stage2_503of503/` and `.../20261116T133739Z_stage0/`. Evaluator outputs:
`docs/hw/results/stage2_eval/` (h2.md/h2.json, h3.json, h5.json), produced locally by the frozen evaluators.
Stand-in model labels apply to every number below (FeFET compact model, literature-cited t_clk and area).

## Freeze decisions (pre-Stage 2 review open MINORs)
| MINOR | Decision | Type |
|---|---|---|
| 2 R99 floor | R99 = max(1, ln 0.01 / ln(1-p)) | correctness fix |
| 4 area/quality | registered: area +-5 % deterministic; quality = success-diff CI vs +-1 pp; "inconclusive" never a win | conservative |
| 6 H5 escalation | ours H5 nominal vs its own H5 dev_x0 (H2 i7i10 comparison reported only) | correctness fix |
| 7 supply pricing | energy rows x V^2 for every machine (ours, B1, B3) | correctness fix |
| 9 B1 ADC re-pricing | labelled cost-only approximation at sigma > 0; H3 pass also needs the win fraction on exact cells | conservative |

## Data integrity
12 692 scored records: 0 NaN, 0 zero-work records, no timeouts; every Stage 2 job ended rc=0. The cloud `frozen.json`
(old evaluator) equals the one recomputed locally with the frozen evaluator. Suspicious, not a data defect but flagged:
every I7 arm collapses to near-zero success (see H2); ETS99 ratios of 0.000 [0,0] arise only where the comparator never
succeeded (ratio = finite / inf), so those "wins" are degenerate.

## Calibration / H0 status
| Baseline | Status | What it limits |
|---|---|---|
| B1 Yin MESA, attempt 2 (P4.02 + P4.02a) | **FAIL**: T1 -28.3 % (k1_e10) / -30.3 % (k4_e10) vs +27 +-10 %; T2 speed-up 6.9x / 14.2x vs ~2x. Registered repair attempt, not an expected pass (T1 unattainable: our SA is already converged) | B1 is our implementation of MESA, not a reproduction of Yin; "beats B1" means beats our tuned FeFET CiM annealer |
| B3 Fujitsu DA (P4.04) | implementation verified (T3 pass 1.02); scaling not reproduced (T1 0.0073, T2 0.0081 outside bands; T4 47.5 FAIL) | B3 is a digital-annealer stand-in, not Fujitsu's measured machine |
| B2 HyCiM D-QUBO (P4.05) | DONE-NEG: D-QUBO 0 % in every diagnostic reading vs filter ~30 %; not in band | B2 only on QKP; no cross-problem comparison with ours |

## H2 verdict (registered gate): **FAIL**
"A restart rule is not a hardware win over a tuned FeFET CiM annealer; the phase stops before H4." Wins over B1-tuned
on energy appear in Max-Cut only (2 families required). Full design selected by freeze = `ours_none_off` (no tweak).

ETS99 ratio vs B1-tuned (`3_B1_best` = B1 with no restart), [95 % CI], energy verdict / success diff:
| Arm | Max-Cut | MaxSAT | Colouring |
|---|---|---|---|
| ours none (off) | 0.652 [0.652,0.652] win / +0 | 0.953 tie / +0 | 1.059 loss / +0 |
| ours none + I10 | 0.652 win | 0.953 tie | 1.059 loss |
| ours da_offset | 1.13 loss / -18 pp | n.e. (0 % success) | 63.8 loss / -91 pp |
| ours mesa | n.e. (0 % success) | n.e. | 12.9 loss / -74 pp |
| ours kc2 | 1.20 loss / -19 pp | n.e. | 43.4 loss / -87 pp |
| ours kc2 + I11 | 0.273 [0.12,0.67] inconclusive (Holm p 0.10) / -13 pp | 3.85 inconclusive / -8 pp | **0.050 [0.029,0.060] win** / +0 |
| ours kc2 + I11 + I10 | 0.271 inconclusive / -13 pp | 3.85 inconclusive | **0.037 win** / +0 |
| ours none + I7 (and I7+I10) | n.e. (0 %) / -69 pp | n.e. / -9 pp | n.e. / -100 pp |
| ours kc2 + I11 + I7 (+I10) | n.e. / -69 pp | n.e. / -9 pp | 0.18 / 0.12 inconclusive / -91 pp |

Rung contrasts: I10 vs off = tie in all three families (ratio 0.999-1.000); Kc2 vs MESA (2d vs 2c) = degenerate "win"
on Max-Cut (MESA 0 % success), not evaluable on MaxSAT (both 0 %), loss on colouring (3.37) -> rung 2d "tie (not better)".
vs B3 (digital): ours none loses on Max-Cut (2.08 inconclusive; ours kc2 3.85 loss), wins MaxSAT/colouring only because
B3 has 0 % / 9 % success there (degenerate). Area: ours is 0.68-0.80x B1 on Max-Cut but 1.06-1.66x on MaxSAT/colouring,
1.13-1.93x B3 everywhere. B2 (QKP filter arm): success 11 % at 10^4, 44 % at 10^5 proposals; ETS99 1.9e9 / 4.0e9 fJ.

## H3 sensitivity: **not run** (registered: H3 runs only after an H2 win). The 52 H3 trajectory files exist but are not scored.

## H5 variation: **not informative**
Every H5 arm (ours kc2/mesa/none + I7, kc2+I7+I10, T7, B1 mesa) has 0 % success at nominal and at the ideal point
dev_x0 on Max-Cut and MaxSAT, so all 10 %-loss points are inf, the Kc2/MESA ETS ratio is nan at every point and no
escalation fires (0 vs 0). This is the I7 / MESA floor effect from H2, not robustness. Corners not evaluable (no
corner card); endurance n/a (0 array writes). B3 supply (Max-Cut ETS99 x V^2): 2.47e11 / 3.01e11 / 3.61e11 fJ at
0.9/1.0/1.1 V. B2 QKP: success 0.53 nominal, 0.40 dev_x0, 0.47 dev_x2, 0.20 dev_x4 (15 runs each; false-accept
states rise 0 -> 298 per run with device sigma).

## Plain-language summary
- Our design does **not** win on energy-to-solution at equal success against B1-tuned on >= 2 families: it is 35 % cheaper
  on Max-Cut (same trajectory, cheaper cost table: no-tweak arm), a tie on MaxSAT (4.7 % cheaper, under the 5 % margin)
  and 6 % worse on colouring. Against B3 it loses on Max-Cut; its MaxSAT/colouring "wins" rest on B3 failing to reach
  the target. B2 is QKP-only and not comparable.
- Effect carriers: none of the restart arms (da_offset, mesa, kc2) helps; MESA never reaches the Max-Cut target. I10 is
  energy-neutral (<= 0.1 %). I7 breaks the solver (success -9 to -100 pp; needs a bug/design review before any re-run).
  I11 + Kc2 is the only strong signal: 20-27x lower ETS99 on colouring at equal (100 %) success, ~3.7x on Max-Cut but
  with 13 pp lower success (inconclusive), worse on MaxSAT. I3 and I5 were not in the scored Stage 2 ladder (I3
  knapsack only; I5 only if I11 fails), so nothing is claimed for them.
- Robustness: H3 not run by rule; H5 floored at 0 % success, so no robustness statement is possible.

## Limitations
- I10 savings are only ADC bias and skipped-read time; trajectories are identical by construction.
- t_clk and area are placeholder-free but literature-cited, not measured or signed off.
- B1 (Yin MESA) and B3 (Fujitsu DA) do not reproduce their papers; B2 D-QUBO reproduction negative. All comparisons are
  against our implementations of these designs, so no claim about the published chips follows.
- MaxSAT success is <= 9 % for every arm (self-referenced targets), so MaxSAT verdicts are weak.
- Seeds/instances: 10 instances per family; several CIs are degenerate because arms share trajectories.

## Author items
Tag a5f2866 if accepted; review I7 (suspected implementation/design fault); decide whether an I11+Kc2-centred,
colouring-specific H2 amendment is worth registering (would be a new prereg, not a rescue of this one).
