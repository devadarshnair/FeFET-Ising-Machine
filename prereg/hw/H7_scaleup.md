# H7 prereg: Stage 4 scale-up of L1 (colouring) with published software references

**FROZEN by this commit (17 Nov 2026 IST), before any Stage 4 data, after independent internal review (go at 14da908). Untagged.**
Code that implements it: scripts/testing/plan_h7.py (design as data), h7_instances.py, gen_jobs_stage4.py, evaluate_h7.py, cost_model.MeasuredCost,
run_cell.py `--h7-cfg` / `--smoke-h7`, scripts/baselines/sw_colouring.py, pricing.b1_native_fs_bits, machines.drive_sw.
Preregs H0-H6 and amendment 1 are not changed.

## 0. Status of the lead (read first)
L1 (Kc2 + I11 beats B1 on planted colouring) was confirmed in Stage 3 at 120 spins on two fresh families (ETS99 ratio 0.143 and
0.003; success +8 and +92 pp; docs/hw/results/STAGE3_RESULTS.md). The effect comes from I11 (Kc2 alone scored 0 %). H7 asks
whether L1 survives larger N, a benchmark-style family and a fair default ADC for every machine, and how it compares with published
software. Only fresh Stage 4 data count; nothing is pooled with Stages 2-3.

## 1. Hypotheses
- **H7-S1 (primary, per size).** At N in {240, 480, 960} spins, ours Kc2 + I11 (fs ADC) has an ETS99 win (rule of section 5) over
  the B1 comparator (fs ADC) on BOTH planted families of that size (p3nN: 3-colourable, degree 4.5; p4nN: 4-colourable,
  degree 8; H6 generator). **Scale verdict** = the largest N such that L1 holds at every size up to N.
- **H7-S2 (benchmark-style family).** Same contrast on 'dimacs': myciel4/5/6 and queen5_5/6_6/7_7/8_8 at k = chromatic number
  (115-665 spins), rebuilt from the definitions (section 3).
- **H7-S3 (reported per family).** ours none (fs) vs the B1 comparator (the L2 cost-only effect on colouring), ours Kc2 + I11 vs B3
  (digital DA), ours Kc2 + I11 vs ours none (does I11 still carry the effect at scale).
- **H7-S4 (software references, quality only).** Success difference of ours Kc2 + I11 vs (a) dwave-samplers SA on the same QUBO at the
  same sweeps, (b) TabuCol at as many iterations per vertex as the family's sweeps, (c) DSATUR (one deterministic run). No energy is compared with software.
  Expectation stated in advance: TabuCol reaches proper colourings far more often (local timing: it solves most instances in < 1 s).
- **H7-V (report-only).** Variation at the confirmed design point (section 4).

## 2. One cost rule: full-scale ADC for every machine
ADC bits = bit length of the largest column current the programmed array can produce (max column sum), exact (LSB 1), for every
analog machine. Ours: `ours.<restart>.fs` simulates the fs ADC (CimCfg.fs; noise above full scale clips), no I7/I10. B1: native
multilevel cells, max over 32-row tiles, lanes and polarities of the summed levels (`pricing.b1_native_fs_bits`), applied in
`pricing.price` for `b1.*.fs`. B1's fs ADC is also simulated: every 32-row tile's ADC full scale is set to its largest bit-plane column
sum (`machines.b1_tile_fs`), so read noise above full scale clips exactly as in ours (noise-free trajectories are unchanged; test_h7
checks both). B3 is digital (no ADC). Ours' fs is taken over the whole column (n_pad rows),
B1's per 32-row tile: conservative for ours.

**Pricing table (registered before any Stage 4 record is read).** The **PRIMARY** pricing, and the one every verdict (win / tie /
loss, the scale verdict, the kill rule) uses, is `measured_v1` (timing study v1, docs/hw/results/TIMING_AREA_V1.md) with the clock and
restart-unit policy below (`cost_model.MeasuredCost`; rows in docs/hw/energy_table_measured_v1.csv and
docs/hw/energy_table_measured_v1_blocks.csv). The **canonical** table (2 ns, 1.88 um2, 3.29 nW) is a stated secondary sensitivity,
and so is `baseline_lane_path_clock` (below). `h7_report` carries all three; a sensitivity whose scale verdict differs from the
primary is flagged, and the primary is not changed by it. timing study v1 showed that the table can flip a verdict (Max-Cut L2 0.652 -> 1.09).
- **Clock policy.** Each machine runs at its own t_clk = max(select-tree path at its padded N, lane path 2.41 ns, RNG path 2.32 ns),
  the select-tree path log-log interpolated between the synthesised N = 64 / 256 / 1024 (3.18 / 5.64 / 9.15 ns; so 256 lanes 5.64 ns,
  512 about 7.2 ns, 1024 9.15 ns). Ours: its synthesised select tree. B1 and B3 were **never synthesised**: the primary assumes
  both use the same single-cycle N-wide select tree at their own padded N. This is a stated limitation. Sensitivity
  `baseline_lane_path_clock`: B1 and B3 at the 2.41 ns lane-path clock (no N-wide select tree), ours unchanged; this is the
  adversarial case for ours and is reported next to every verdict.
- **Restart unit.** Any arm with a restart unit is charged timing study v1's measured post-P&R restart_unit area and leakage at its padded
  N (area 10,131 / 37,887 / 173,681 um2 and leakage 0.24 / 0.95 / 4.48 mW at N = 64 / 256 / 1024, log-log between): ours `kc2` and
  B1_mesa_epoch (`mesa`); arms `none` and B3 pay nothing. Kc2 is charged the full unit (perm table + MESA encoder as synthesised),
  an upper bound, because no Kc2-only build was synthesised; the stall counter remains priced at its canonical dynamic energy. The
  unit's dynamic energy was not measured and is not added (stated limitation). Under the canonical sensitivity no unit is charged.

## 3. Instances, seeds, budget
| Family | TEST instances | Spins (lanes) | Sweeps | Seeds |
|---|---|---|---|---|
| p3n240 / p4n240 | planted seeds 801-810 / 901-910 (n = 80 / 60) | 240 (256) | 150 | 10 |
| p3n480 / p4n480 | planted seeds 801-810 / 901-910 (n = 160 / 120) | 480 (512) | 300 | 8 |
| p3n960 / p4n960 | planted seeds 801-805 / 901-905 (n = 320 / 240) | 960 (1024) | 600 | 6 |
| dimacs | myciel4, myciel5, myciel6, queen5_5, queen6_6, queen7_7, queen8_8 | 115-665 | max(150, 150 x spins / 240) per graph: 150 / 176 / 416 / 150 / 158 / 214 / 360 | 10 |
Planted: optimum 0 by construction. DIMACS graphs are generated (queen: same row/column/diagonal; myciel: Mycielski construction from
C5); tests check vertex/edge counts against the DIMACS headers and identity (queen) / isomorphism (myciel) with a local copy of the
DIMACS files (read only, never executed); no benchmark file ships with the payload. Target everywhere: energy 0 (proper k-colouring).
**p3n960 is kept** (not dropped): ours is probably at or near 0 % there (pilot 5 end conflicts), in which case the family is "not evaluable" and the 960 size ends the scale verdict at 480; the cost is accepted and stated (10 of 43.6 CPU-h, about Rs 29).
Seed stream: Spec.tag = 7, inst_index 300+ (disjoint from Stages 2-3). **Budget scales with N**: sweeps = 150 x N / 240.
DIMACS budgets scale per graph with the same per-spin rule (floor 150 sweeps; TabuCol iterations per vertex follow); the per-instance success of every arm is printed in the report. No pilot on DIMACS exists; queen graphs may be 0 % for every hardware arm.
Pilot (16 Nov IST, TUNE-only instances p3 seed 851, p4 seed 951, never in TEST, 1 seed each, end conflicts): 480 spins at 150 sweeps
ours Kc2+I11 2 (p3) / 0 (p4), B1_best 1 / 5; at 600 sweeps ours 1 / 0, B1 3 / 1; 960 spins at 600 sweeps ours 5 (p3). TabuCol at
the scaled budget (iterations per vertex = sweeps) reached 0 conflicts in 4/4 seeds on p3n480, p3n960 (two instances) and p4n960, so
no size is not-evaluable by construction for the best arm; the planted 3-colourable families at 480/960 may still leave every hardware
arm at 0 %, in which case the hardware contrast there is "not evaluable" (section 5). Seeds and instances are trimmed with N (table).
No tuning: configs are the Stage 2 colouring selections (docs/hw/results/stage2_eval/tuned.json, sha256 prefix 9b96c4c567b29820) and
B1_mesa_epoch exactly as Stage 3 (K = 1 epoch of 10 sweeps). TabuCol reference at 20x (3000 iterations per vertex, 3 seeds) gives
per-instance solvability; it is not a contrast.

## 4. Arms
TEST: ours_kc2_i11 (`ours.kc2.fs.i11`), ours_none (`ours.none.fs`), B1_best (`b1.none.fs`), B1_mesa_epoch (`b1.mesa.fs`; not
at 960 spins, for cost: it scored 0 % on both Stage 3 colouring families), B3 (`b3.b3`), SW_sa (same sweeps), SW_tabucol (iterations
per vertex = the family's sweeps), SW_dsatur. **B1 comparator** per family = the B1 arm with the lower observed ETS99 (favours B1).
H7-V: ours_kc2_i11 and B1_best on p3n240 and p4n240, first 3 TEST instances x 10 seeds, points nominal, dev_x0, dev_x2, dev_x4,
read_x2, write_x2, mismatch_x2, drift_0.02, temp_85, combined (H5 definitions, plan.H5_POINTS).

## 5. Statistics and decision rules (H2/H6 rules, unchanged)
Paired two-level bootstrap (instances, seeds within), 10 000 resamples, 95 % percentile CIs; ETS99 with R99 = max(1, ln 0.01 /
ln(1-p)). **Win**: ETS99 ratio <= 0.95, Holm p < 0.05, CI upper < 1, success diff >= -1 pp (point and CI lower bound). **Tie**: success
CI inside +-1 pp and ratio CI inside [0.95, 1.05]. **Loss**: ratio >= 1 with CI lower > 1. Otherwise inconclusive. A comparator at 0 %
success gives "not evaluable", never a win (the evaluator enforces it per contrast: comparator observed success 0 -> verdict "not
evaluable (comparator at 0 % success)", even if ours succeeds; the success difference is still reported as a quality fact). **Holm** over the 4 registered hardware contrasts of each family (evaluate_h7.HW_CONTRASTS);
families reported separately. Software contrasts: success-difference CI with the quality rule (+-1 pp), no Holm, no energy.
**Kill / scope rules.** L1 is *not replicated* if it is not a win on both 240-spin families. The *scale lead is killed* at the first
size where either planted family is not a win (the verdict names that size). If every hardware arm is at 0 % on a family, that family
is "not evaluable" and no claim is made at that size. Losing to TabuCol on quality does not touch the hardware claim but must be stated
next to it ("a published software heuristic reaches proper colourings more often at an equal move budget").
H7-V: report success and mean end conflicts per point; escalation flag if nominal success < ideal (dev_x0) - 1 pp.

## 6. Power (stated, not a guarantee)
Runs per arm: 100 at 240 spins, 80 at 480, 30 at 960, 70 on dimacs. Success CI half-widths are roughly 6-10 pp (240), 7-11 pp (480)
and 12-18 pp (960) at mid success, so a win at 960 needs ours far ahead of B1 (as at col4p in Stage 3, +92 pp) or both near 100 %;
a moderate effect at 960 will read inconclusive. With 5 instances the instance-level bootstrap at 960 is coarse. ETS99 ratios with
both arms near 100 % are narrow (Stage 3). Mean end conflicts are the graded secondary.

## 7. Compute
Per-run cloud seconds: local timing on p3n960 (16 Nov IST) x 1.5 margin x plan.CLOUD_OVER_LOCAL, scaled by spins x lanes x
sweeps / 150. gen_jobs_stage4.budget(): jobs 43.6 CPU-h (test 38.1, ref 2.0, var 3.5; DIMACS planned per graph), x 1.15 + 12 vCPU-h gate = **62.2 vCPU-h,
about Rs 125 at Rs 2.01 / vCPU-h, ~1.9 h wall on 32 vCPU** (cap 75 vCPU-h / Rs 150). Gate: STAGE0_GREEN at the pinned commit
(tests/hw, smoke_all, smoke-h6, `run_cell.py --smoke-h7` incl. the report barrier).

## 8. What would change this file
Any change after the freezing commit needs a new committed revision before any Stage 4 record is read.
