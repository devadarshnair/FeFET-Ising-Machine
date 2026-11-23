# Stage 4 (H7 colouring scale-up) results

Rules: prereg/hw/H7_scaleup.md (frozen 151b99c) + prereg/hw/H7_amendment1.md (61dcc1d: sizes 240 and 480 only), both committed
before any Stage 4 data. Run pin 61dcc1d, cloud gate STAGE0_GREEN at that pin. 158/158 jobs rc 0 (report_h7 barrier rc 0), 157 raw
job files, 4398 records. Return package 00_admin/cloud_cpu_return/20261116T214925Z_stage4_158of158/ (SHA256SUMS verify). All
numbers come from stand-in BSIM4 / FreePDK45 cost models: ratios only, absolute values about x2 uncertain.

Eval tables: docs/hw/results/stage4_eval/ (h7_report.json, h7_report.md; copies of the cloud output).

## Checks done before reading
- **Evaluator reproduced.** `evaluate_h7.py --raw sim/out/hw/stage4` re-run locally on the unpacked raw data (sim/out/hw/stage4,
  gitignored): h7_report.json is identical to the cloud output (JSON equality) and h7_report.md matches.
- **Data sanity.** No NaN/Infinity in any raw file, no zero-step run, no duplicate (seed, spec, arm) record, no dirty tree, every
  file at pin 61dcc1d, no timeout or non-zero rc in Stage 4 (the two rc 1 lines in queue.log are Stage 0 attempts before the gate
  passed). Every record is seed stream tag 7, instance index 300+ (fresh, disjoint from Stages 2-3).
- The only NaN in the report is `ours_none vs B1_best` on p4n240, where both arms are at 0 % (expected; not a contrast that matters).

## L1: ours Kc2 + I11 vs B1 (comparator B1_best on every family) and B3

ETS99 ratio (ours / B1) [95 % CI], Holm p, verdict. Success diff is the same under every pricing.

| family | success ours / B1 | success diff [CI] | measured_v1 (primary) | canonical | baseline_lane_path_clock |
|---|---|---|---|---|---|
| p3n240 | 0.58 / 0.45 | +0.13 [-0.05, +0.31] | 0.490 [0.22, 0.76], p 0.004, **inconclusive** | 0.248 [0.11, 0.39], inconclusive | 0.773 [0.35, 1.20], p 0.21, inconclusive |
| p4n240 | 0.69 / 0.00 | +0.69 [+0.51, +0.85] | **not evaluable** (B1 at 0 %) | not evaluable | not evaluable |
| p3n480 | 0.16 / 0.18 | -0.01 [-0.16, +0.14] | 0.912 [0.26, 1.84], p 0.51, **inconclusive** | 0.517 [0.15, 1.04], inconclusive | 1.505 [0.44, 3.04], inconclusive |
| p4n480 | 0.24 / 0.13 | +0.11 [-0.03, +0.26] | 0.320 [0.07, 0.73], p 0.011, **inconclusive** | 0.177 [0.04, 0.40], inconclusive | 0.522 [0.11, 1.18], inconclusive |

p3n240 and p4n480 fail the win rule only on the success condition (CI lower bound below -1 pp); the ETS99 CI is below 1 under the
primary pricing. Under the adversarial lane-path clock the ETS CI also crosses 1 there. **No sensitivity flips a verdict** (all three
pricings give scale verdict None; `sensitivity_verdict_differs` empty).

vs B3: ours 0.16-0.69 success, B3 0 % on all four families: not evaluable on energy, quality win everywhere (B3 non-reproduction
caveat applies). Kc2 vs ours_none: same pattern as vs B1 (B1_best and ours_none produce identical trajectories, as in Stage 3), win
on quality only on p4n240 (+69 pp).

**Scale verdict (primary): None.** **Kill rule: L1 is not replicated** (no win on either 240-spin family; p3n240 inconclusive, p4n240
not evaluable), so the scale lead is killed at 240. Holm was applied over the 4 registered hardware contrasts per family.

## DIMACS (myciel4-6, queen5_5-8_8; reported, separate family)
Ours Kc2 + I11 0.90 success vs B1_best 0.13 (ETS99 ratio 0.003 [0.000, 0.006], Holm p 0.0004): **win** under all three pricings
(canonical 0.002, lane-path 0.005). Area is a **loss** (ratio 1.10 vs B1, 1.80 vs B3) because the full restart unit is charged.
Per graph ours: 1.0 on myciel4-6 and queen5_5-6_6, 0.7 queen7_7, 0.6 queen8_8; B1_best/ours_none 0.9 on myciel4, 0 elsewhere;
B1_mesa_epoch and B3 0 everywhere. This is a family the prereg reports but does not use for L1 or the scale verdict.

## Software solvers (success only, same move budget)
| family | ours | SW_sa | SW_tabucol | SW_dsatur |
|---|---|---|---|---|
| p3n240 | 0.58 | 0.09 (win) | 1.00 (loss) | 0.10 (win) |
| p4n240 | 0.69 | 0.06 (win) | 1.00 (loss) | 0.20 (win) |
| p3n480 | 0.16 | 0.00 (win) | 1.00 (loss) | 0.00 (win) |
| p4n480 | 0.24 | 0.01 (win) | 1.00 (loss) | 0.00 (win) |
| dimacs | 0.90 | 0.40 (win) | 1.00 (inconclusive, -10 pp) | 0.57 (win) |

A published software heuristic (TabuCol) reaches proper colourings more often at an equal move budget on every planted family.
TabuCol at 20x solves 100 % of TEST instances, so no family is unsolvable by construction.

## H7-V variation (p3n240, p4n240; 3 instances x 10 seeds; report-only)
Success at nominal stand-in variation is **0 % for both arms on both families**; at ideal (dev_x0) ours 0.53 / 0.70, B1_best 0.40 / 0.00.
Escalation flag (nominal < ideal - 1 pp) is raised for ours on both families and for B1 on p3n240. Ours keeps fewer end conflicts
than B1 at every point (for example nominal 12.3 vs 30.5 on p3n240, 7.8 vs 25.3 on p4n240), but no point except dev_x0 gives any
proper colouring. All TEST results above are therefore ideal-device results.

## What holds and its limits
- Holds: at 240-480 spins Kc2 + I11 gives lower ETS99 point estimates than B1 under the primary pricing on three of four planted
  families and a large success lead on p4n240 (B1 at 0 %), plus a clear win on DIMACS. None of this meets the registered L1 win
  rule on the planted families, so **L1 does not scale-replicate**; the Stage 3 120-spin result stays a 120-spin result.
- Limits: simulated designs on one shared stand-in model; our implementations of B1/B3 (no reproduction of their published
  numbers; B3 and B1_mesa_epoch at 0 % everywhere); B1/B3 assumed to use the same N-wide select-tree clock (lane-path sensitivity
  weakens ours, no verdict flip); Kc2 charged the full restart unit (upper bound; drives the DIMACS area loss); unit dynamic energy
  not added; ideal-device TEST runs, and nominal variation gives 0 % success; TabuCol dominates on quality; no claim at 960 spins.
