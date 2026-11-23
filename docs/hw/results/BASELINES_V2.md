# BASELINES_V2: baseline faithfulness, published-figure reproduction, equal tuning (checklist A1-A8)

Prereg: `prereg/calib/P4_v2_reproduction.md` (commit d1012b8, sha256 4fbda83b3dc5..., committed before any scored run; every
RESULT line prints it). All numbers come from stand-in BSIM4 / FreePDK45 cost models: ratios only, absolute values carry about x2
uncertainty. Earlier calibrations (P4.02/P4.02a/P4.04/P4.05/P4.06) are unchanged history.

## 1. What each paper used, and every deviation found

### B1 Yin 2024 (FeFET CiM + MESA; Nat. Commun. 15:2419, PMC10948773 + SI)
| # | Paper | Our implementation before | Now |
|---|---|---|---|
| B1-1 | One proposal per iteration ("flipping a few bits"); energy from one array read; no parallel trial or select tree | Shared parallel-trial machine (all lanes try, one flip is picked by the select tree). This is stronger than Yin | **B1_yin** (`scripts/baselines/b1_native.py`, amendment 1): Yin's move set, one tiled-array read per iteration, MESA v2, priced by the unchanged pricing (native 3-bit cells, fs ADC), own clock. Arms `b1y.sa` / `b1y.mesa`. The old harness B1 stays as **B1_ours_mesa** (continuity; the stronger, parallel-trial reading) |
| B1-2 | Epoch starts at the previous optimum, T reset; cooling not published | Whole-run cooling + T := T0 reset (P4.02 attempt 1, stuck hot); then per-epoch cooling (P4.02a); then K >= epoch (H6 am. 1) | MESA v2 (`MesaV2Unit`): per-epoch cooling and hold; the trap counter runs only after cooling, so K >= epoch holds structurally |
| B1-3 | The trap counter grows while the energy is stagnant | Stall = no new GLOBAL best | Stall = no new EPOCH best (current-energy trap) |
| B1-4 | Perturbation at the start of an epoch ("few bits") | none (recorded only) | Kick of m in {1,2,3} bits from the best state at each restart |
| B1-5 | "+27 %" vs an SA whose budget is unpublished | Scored as T1 (unreachable: our SA is converged) | Not scored. Report-only: MESA vs SA at 10 / 30 / 100 sweeps on G48-G50 gives 0 / +0.8-2.0 / +1.3-1.5 % |
| B1-6 | No select tree, so the clock is the lane path | Our select-tree clock assumed (same_tree) | Own clock: lane path + ceil(log2 row tiles) adder cycles per read (A7) |
| B1-7 | Coupling bits, ADC bits, Count_max and schedule not published | [U] defaults | Unchanged [U]. Count_max is tuned in {n, 2n} under the equal rule |

### B2 HyCiM (Qian et al., arXiv 2410.14111v1)
| # | Paper | Status |
|---|---|---|
| B2-1 | Filter 98.54 % (40 Billionnet-Soutif, 1000 init x 100 runs x 1000 iterations, >= 0.95 opt). The paper defines an iteration as one proposal: "During each SA iteration, the SA logic generates an input variable configuration" (Sec. 3.1; Sec. 3.4 / Fig. 6b) | **Not reproduced under the paper's definition**: 16.5 % per run (R4, amendment 2 A). R4b also fails with the paper's full 1000 x 100 design and Fig. 10's per-initial-state scoring: 45.0 % per initial state (16.4 % per run). The 99.43 % comes from reading an iteration as a sweep of 100 proposals. The paper text contradicts that reading, so it is kept only as a labelled alternative |
| B2-2 | Move set, schedule, T0 not published | v3 settings (swap + flip, S4). They were chosen in the reference software study with the paper number in view (label kept) |
| B2-3 | D-QUBO 10.75 % | Not reproduced under 5 registered readings (P4.05 DONE-NEG, unchanged); B2 enters through the filter arm |

### B3 Fujitsu DA (Aramon et al., arXiv 1806.08815v3)
| # | Paper | Before | Now |
|---|---|---|---|
| B3-1 | Linear-in-beta schedule, T updated every iteration | Harness: geometric (RTL temp_sched) | `b3.b3v2`: lin-beta (golden override, as P4.04) |
| B3-2 | Dynamic offset OFF in the final runs ("indifferent") | Tuning knob = offset on/off (an inert knob) | Offset off; the knob is T_final (B3-3) |
| B3-3 | Th/Tl chosen by a grid search around the 5-10th / 80-85th percentile | T_end >= p5 of \|dE\|; p5 = 1 LSB on integer colouring energies, too hot to freeze | Equal search space: T_final in {T_end, T_end^2/T_start}, the same final temperatures ours' "none" arm reaches |
| B3-4 | Annealing-mode DA, 100 runs from x = 0, no replicas (the PT-DA is a separate machine with PT moves on a CPU) | Same | Same (nothing to add: replicas/PT are not part of the benchmarked DA) |
| B3-5 | Table I temperatures (SK-bimodal 40/4; SK-Gaussian 2e5/1e4 at J x 1e5) | Percentile rule | R3 uses Table I (scaled to sigma = 10) |
| B3-6 | TTS: anneal length optimised per size, Jeffreys posterior, PT/exact reference | Fixed L = 400 n + optimal stopping time; empirical p; self-referenced E* | Optimal L over {25..800} n, Jeffreys theta; E* = best over all runs + 4000 n reference runs (still self-referenced) |
| B3-7 | Sizes 64-1024, 100 instances | 64-256, 20 instances | Same locally; 512/1024 written up as a cloud job (section 5) |
| B3-8 | Fig. 2 boost measured at constant T after 1e5 thermalisation sweeps | T4 measured during the anneal at T_l (the boost is not near N there) | R2: Fig. 2 protocol |
| B3-9 | 16 b couplers / 26 b biases | Computes on the 10/12 b datapath; costed at 16/26 b | Unchanged compute (exact on these instances). The lane is now synthesised at the DA widths for the clock |
| B3-10 | Colouring at 0 % in Stage 4 | Suspected encoding problem | **Not encoding.** B3 and ours.none at schedule fraction 1.0 give identical trajectories (35 = 35 conflicts). The cause is B3-3 (search space) |

## 2. Reproduction status (prereg P4_v2; `scripts/baselines/repro_v2.py`; raw sim/out/hw/baselines_v2/, results docs/hw/results/baselines_v2/p4v2_result.json)
| Target | Result | Verdict |
|---|---|---|
| R1 B1 Yin SI Fig. S7 (G1, 1200 sweeps, solved = BKS, 40 seeds) | Neither arm reaches BKS on G1-G5 (SA mean 11574 / MESA 11417 of 11624). MESA (10-sweep epochs, ~98 epochs) ends below SA | **FAIL** (not reproduced under the P4_v2 reading) |
| R1b (amendment 1) same, faithful kernel, solved = 0.99 BKS, E in {10, 100} sweeps | G1: SA 100 % (TTS 1181 sweeps). MESA E = 10: 0 %; E = 100: 82.5 % (TTS 1446, ratio 0.82) | **FAIL** (no E meets S_MESA >= 0.90 and ratio >= 1) |
| R3full (amendment 1) B3 exponent over 64-1024 | Registered rule: beta 0.0025 bimodal, 0.0016 Gaussian, both in band. **This PASS is not a valid reproduction.** At 512/1024 (and for Gaussian from 128 on) the 80th-percentile TTS is the Jeffreys zero-success floor at L* = 25 n: TTS80 is 5.98e6 at 512 and 1.20e7 at 1024 for both classes, i.e. linear in n by construction. Aramon only report a percentile when at least that share of instances is solved; the registered rule left that condition out | **PASS by rule, flagged invalid** |
| R3 post-hoc (labelled, not registered): Aramon's condition added (>= 80 % of instances solved at the chosen L) | Bimodal beta **0.0030** over 64-1024 (band 0.00105-0.0042; paper 0.0021). Gaussian: below 80 % solved from n = 256 at our 50-run / 800 n budget, so the exponent cannot be estimated | bimodal consistent post hoc; Gaussian n.e. (`baselines_v2/r3_posthoc_80pct_solved.json`) |
| R2 B3 Aramon Fig. 2 (N = 64, constant T) | Pp/Ps = 64.0 at the lowest T and 1.006 at the highest, monotone, both classes | **PASS** |
| R3 B3 TTS80 exponent (64-256, Table I, optimal L, Jeffreys) | beta 0.0053 bimodal (band 0.00105-0.0042), 0.0069 Gaussian (0.00095-0.0038); was 0.0073 / 0.0081. L* sits at the shortest anneal in the grid (50 n / 25 n), so the restart regime dominates at these sizes | **FAIL** (closer; needs 512-1024, cloud) |
| R4 B2 HyCiM filter 98.54 % (relabelled by amendment 2 A: iteration = one proposal) | 16.46 % per run at 1000 proposals. Alternative reading the paper text contradicts (iteration = sweep): 99.43 % | **FAIL** |
| R4b (amendment 2 B) paper design 1000 init x 100 runs x 1000 proposals, Fig. 10 per-initial-state reading | 45.0 % per initial state, 16.4 % per run; worst instance jeu_100_75_5 at 0.2 % | **FAIL** |
| R5/R6 equal tuning + B3 colouring | see section 3 | |

## 3. Equal tuning (A6) and B3 colouring (A4)
Rule (prereg s.5): every hardware arm gets 8 configs = 4 shared (T_start, T_end) percentile pairs x 2 values of one secondary
knob, the same Stage 2 TUNE split, TUNE_SEEDS = 2, and the select_tuned rule. `tests/hw/test_baselines_v2.py::
test_harness_grids_are_eight_configs_each` locks the grid sizes and the shared pairs for every arm.
Selected configs (`docs/hw/results/baselines_v2/tuned.json`; 8 configs per arm, Stage 2 TUNE split, select_tuned rule). Colouring:
b3.b3v2 p90/5 with T_final = T_end^2/T_start; b1.mesa2 p75/5 K = 2n; b1y.sa p75/5 fraction 0.5; b1y.mesa p75/5 K = 2n.

R6, success = proper colouring (Wilson 95 %); raw sim/out/hw/baselines_v2/test/h7, `docs/hw/results/baselines_v2/r6_result.json`:
| family | **B3 v2** | B1_ours_mesa v2 | B1_yin SA | B1_yin MESA | Stage 4: ours Kc2+I11 | B1_best | old B3 |
|---|---|---|---|---|---|---|---|
| p3n240 | **0.85** [0.77, 0.91] | 0 | 0 (6.8 conflicts) | 0 | 0.58 | 0.45 | 0 |
| p4n240 | 0 (7.6 conflicts) | 0 | 0 | 0 | 0.69 | 0 | 0 |
| p3n480 | **0.69** [0.58, 0.78] | 0 | 0 | 0 | 0.16 | 0.18 | 0 |
| p4n480 | 0 | 0 | 0 | 0 | 0.24 | 0.13 | 0 |
| DIMACS | 0.14 [0.08, 0.24] | 0 | 0 | 0 | 0.90 | 0.13 | 0 |

**RESULT P4v2 R6 PASS: B3 solves colouring once it gets the same tuning search space** (A4). **Consequence for the claims:** on
the 3-colouring planted families the properly tuned DA baseline reaches proper colourings more often than ours Kc2+I11 (0.85 vs
0.58 at 240, 0.69 vs 0.16 at 480; success only in this table; energy under measured_v2 is in the "R6 energy under measured_v2" table below, from `docs/hw/results/baselines_v2/r6_energy_measured_v2.json`, where B3 v2 is also ahead on energy). On 4-colouring and DIMACS ours stays ahead. The Stage 4
"quality win everywhere vs B3" no longer holds; it came from an under-tuned B3. H7 is closed and is not re-scored here, but
STAGE4_RESULTS and any paper text must carry this. The faithful B1_yin solves nothing at 150 sweeps, in either arm. The B1
comparator that matters remains B1_best (parallel-trial core, no restart), which is stronger than Yin's own algorithm.

### R6 energy under measured_v2 (amendment 2 D; `scripts/baselines/r6_energy.py`, `docs/hw/results/baselines_v2/r6_energy_measured_v2.json`)
MeasuredCostV2() defaults (timing study v2 primary, accepted at fce3e6f). ETS99 ratio X / B3 v2 (> 1: B3 v2 spends less energy per expected
success) [95 % bootstrap CI, B = 2000], d_success = X - B3 v2:
| family | ours Kc2+I11 / B3 v2 | ours none / B3 v2 | B1_best / B3 v2 |
|---|---|---|---|
| p3n240 | **2.59** [1.53, 4.04], d_success -0.27 | 4.28 [2.73, 8.55], -0.40 | 5.23 [3.34, 10.45], -0.40 |
| p3n480 | **7.94** [3.25, 16.74], -0.53 | 7.04 [3.86, 20.35], -0.51 | 9.05 [4.91, 26.60], -0.51 |
| p4n240 / p4n480 | B3 v2 at 0 %: not evaluable; ours +0.69 / +0.24 success | ours none 0 % / +0.12 | 0 % / +0.12 |
| DIMACS | **0.008** [0.000, 0.017], +0.76 | 3.30 [2.14, 4.26], -0.01 | 2.82 [2.02, 3.68], -0.01 |
**On the 3-colouring families the tuned DA baseline beats ours on energy as well as success. The CIs exclude 1 at both sizes.** Ours
wins clearly on DIMACS and is the only machine that solves the 4-colouring families. The B3 clock is the same-tree rule (A7: above
N = 64 the tree sets B3's clock, so the own-clock rule gives the same value).

### R6 fairness (amendment 2 C)
Ours Kc2+I11 is greedy (I11: no temperature), so the colder T_final knob does not apply to it. Ours "none" already reaches
T_end^2/T_start through its schedule-fraction knob (and is in the tables above). The new arm **ours.kc2c** is ours Kc2 with
Metropolis acceptance, K = 2n and the B3 v2 knob T_final in {T_end, T_end^2/T_start}, under the same 8-config rule. It was run on
cloud (`00_admin/cloud_cpu/offload/baselines_jobs3.tsv`, pin 93c63fa, 72/72 jobs rc 0). The local re-run of `retune_v2.py select`
gives a tuned.json byte-identical to the cloud copy the test jobs used (`00_admin/cloud_cpu/offload/return/tuned_cloud_batch3.json`).
Colouring selection: p90/5, T_final = T_end^2/T_start, so the colder end was chosen.
| family | ours.kc2c success [Wilson] | ETS99 ours.kc2c / B3 v2 (measured_v2) |
|---|---|---|
| p3n240 | 0.55 [0.45, 0.64] | **3.65** [2.47, 5.97], d_success -0.30 |
| p3n480 | 0.21 [0.14, 0.31] | **8.16** [4.77, 15.45], -0.47 |
| p4n240 | 0 | ours at 0 % |
| p4n480 | 0.15 [0.09, 0.24] | B3 at 0 %: not evaluable (+0.15) |
| DIMACS | 0.14 [0.08, 0.24] | 3.14 [2.16, 3.52], d_success 0.00 |
**With the identical knob range ours still loses to B3 v2 on the 3-colouring families**, by about the same margin as Kc2+I11.
The R6 conclusion is therefore not an artefact of unequal tuning.

### 3b. A5 diagnosis: why HyCiM's 98.54 % is not reached under its own definition
- Budget: 1000 proposals for n = 100 is 10 proposals per item. From a random feasible Monte Carlo start, our SA (v3 move set, S4
  schedule) reaches >= 0.95 opt in 16 % of runs. Even the best of 100 such runs per start reaches it for only 45 % of starts.
- The paper gives no move set, schedule, initial temperature or initial-state sampler (Sec. 3.4 and 4.3). For 98.54 % at 10
  proposals per item, its SA must start much nearer the optimum, or each proposal must carry far more information than a flip/swap
  (e.g. a greedy or multi-bit regeneration), or "success" must be judged on another quantity. None of these can be read from the
  text, so there is no fidelity fix we can justify from the paper. Tuning these knobs until 98.54 % appears would be fitting.
- What is faithful: the formulation, the filter (exact at sigma = 0, P4.06 A1), the instances, the 0.95 x opt threshold, the
  1000 x 100 x 1000 design (R4b) and iteration = one proposal (infeasible proposals consume an iteration, hycim.py `_run`). B2 stays a
  literature-parameterised HyCiM-style filter annealer, not a reproduction.
- Consequence: in our stage results B2 is a QKP-only baseline (H2/H3 used it at 1e4 / 1e5 proposals). No reported contrast depends
  on its reaching 98.54 %.

## 4. Per-machine clock (A7) and cost rule (A8)
- `scripts/baselines/baseline_clock.sh` runs the timing study v1 flow functions, taken from the committed tree (git archive), on our lane
  and on the lane at the DA widths. P&R path: ours **2.409 ns** (timing study v1 2.406: the flow reproduces) and B3 lane **2.687 ns**.
  Rows: `docs/hw/energy_table_baseline_clock.csv`. `OwnClockCost` (scripts/baselines/baseline_clock.py): B3 = max(select tree at N,
  B3 lane), so above N = 64 the tree still sets the clock and the previous same_tree pricing was already faithful for B3.
  B1 = lane path (no tree) + ceil(log2 row tiles) cycles per read.
- Stage 4 re-priced under the own clock (`docs/hw/results/baselines_v2/h7_own_clock.json`). ETS99 ours Kc2+I11 / B1_best:
  p3n240 0.77 [0.34, 1.20], p3n480 1.50, p4n480 0.52 [0.12, 1.21], DIMACS 0.005. These equal the earlier lane_path sensitivity,
  so the primary (same_tree) pricing favoured ours against B1. **Scale verdict unchanged (None).**
- A8: `tests/hw/test_cost_rule_all_tables.py` runs the ADC-bias-per-step, tile-conversion, B3-no-ADC and one-table checks for
  ours/B1/B2/B3 on every name in cost_model.TABLES (canonical, measured_v1, measured_v2). **Run 20 Nov at HEAD after fce3e6f with
  $HOME/miniconda3/envs/swref/bin/python (Python 3.12.15, numba 0.68.0, numpy 2.3.5): 12 passed, 0 skipped**, including all
  4 measured_v2 cases. Whole suite in the same interpreter: `pytest -q -rs tests/hw` -> **538 passed, 0 skipped, 0 failed**.

## 5. Offloaded compute (rented cloud CPU; runs are rsynced back to the same sim/out paths)
- `00_admin/cloud_cpu/offload/baselines_jobs.tsv` (pin da4e16c): the rest of R5 tuning (tune 9-12), select, and the R6
  240-spin test for b3.b3v2 / b1.mesa2. 13 jobs, about 422 CPU-min.
- `00_admin/cloud_cpu/offload/baselines_jobs2.tsv` (pin 5344d30, prereg amendment 1 bb57453): R1b; R3x (n = 512 and 1024,
  120 jobs; C-B3-scale); B1_yin tuning; select (all four arms); R6 240-spin B1_yin; R6 at p3n480 / p4n480 / DIMACS for all four
  arms (C-R6-480). 244 jobs, about 3680 CPU-min, each under 60 min, with one smoke command per job. Three smoke commands were
  checked locally.

## 6. Remaining gaps
- B1: no published figure reproduced (R1, R1b FAIL; +27 % not scorable). The faithful B1_yin exists and is priced, but Yin's Fig.
  S7 depends on unpublished settings (iteration meaning, epoch length, solved criterion).
- B3 scaling: the registered R3full PASS is invalid (zero-success floor). Only the post-hoc bimodal exponent (0.0030) is
  consistent with Aramon. Gaussian would need more runs per instance (around 500) or longer anneals at n >= 256.
- B2 (A5): not reproduced under the paper's iteration definition (R4, R4b FAIL; section 3b). D-QUBO not reproduced.
- A1, A3, A5 are honest FAILs against the target bar. Open: whether to accept them as documented gaps, or to fund the
  Gaussian R3 run (about 500 runs per instance at n >= 256, about 300 CPU-h).
- Stage 4 / H7 text must be corrected for the B3 v2 result (R6), which is the author's decision.

## Internal review
Commits (branch hw/p4-baselines; mine only, interleaved with other tracks): d1012b8 prereg P4_v2; d321e6e B3 v2 + B1 MESA v2 +
kernels + harness hooks; 8c67ecf retune_v2; 1dd3728, 8309000 clock + cost rule; 1965df4 clock tests; Stage 4 own-clock reprice
commit; R1-R4 results commit; bb57453 amendment 1; 5344d30 B1_yin + R1b/R3x runners; a7d5dd1 doc draft; final results commit (this file).

| Checklist item | Claim | Evidence |
|---|---|---|
| A1 | B1 settings re-derived; faithful B1_yin implemented; Fig. S7 attempted twice under a prereg: FAIL | section 1 B1-1..7; `tests/hw/test_b1_native.py` (7); `repro_v2.py eval --parts R1,R1b` -> RESULT lines; p4v2_result.json R1, R1b |
| A2 | Epoch cooling and K >= epoch are structural in MESA v2 and the native kernel; legacy bug kept reproducible | `tests/hw/test_baselines_v2.py::test_mesa2_*`, `test_old_whole_run_mesa_regression_documented`, `test_yin_native_mesa_epochs_respect_cooling*`; test_b1_native::test_mesa_epochs_wait_for_cooling; existing test_h6::test_mesa_sweep_k_is_at_least_the_epoch |
| A3 | B3 matches the paper (lin-beta, offset off, Table I, optimal L, Jeffreys; no replicas in the benchmarked DA). Fig. 2 reproduced; exponent: registered PASS flagged invalid, post-hoc bimodal consistent | R2/R3/R3full RESULT lines; r3_posthoc_80pct_solved.json; test_da_kernel_matches_golden_b3_distribution, test_da_const_t_boost_limits, test_jeffreys_tts, test_aramon_table1_units |
| A4 | B3 colouring 0 % came from the tuning search space, not the encoding; B3 v2 solves colouring | section 1 B3-10; R6 table; `retune_v2.py eval` -> RESULT P4v2 R6 PASS; r6_result.json |
| A5 | HyCiM filter **not reproduced** under the paper's iteration definition: R4 16.5 % (FAIL); R4b with the paper's 1000 x 100 design and per-initial-state scoring 45.0 % (FAIL). Diagnosis in section 3b | RESULT P4v2 R4 / R4b FAIL; p4v2_result.json; prereg amendment 2 (f12ae71) |
| A6 | Equal rule (8 configs, same split, seeds, selector) for every machine, stated in the prereg | prereg s.5; test_harness_grids_are_eight_configs_each, test_b1_native::test_equal_rule_grids; tuned.json |
| A7 | Per-machine clock: B3 lane synthesised and P&R'd at the DA widths (2.687 ns; our lane re-run 2.409 ns); B1 has no tree and pays tile-sum cycles; Stage 4 re-priced, verdict unchanged | baseline_clock.sh/.py; energy_table_baseline_clock.csv; test_own_clock_*; h7_own_clock.json |
| A8 | One cost rule on all 4 machines for every cost table, measured_v2 included: 12/12 pass, 0 skipped | `tests/hw/test_cost_rule_all_tables.py`; full suite 538 passed (interpreter below) |

Interpreter for every command and test: **$HOME/miniconda3/envs/swref/bin/python** (3.12.15, numba 0.68.0, numpy 2.3.5).
The trapmem env also works. The base env and `cim` have no numba, so `tests/hw` cannot be collected there.
Commands: `python -I scripts/baselines/repro_v2.py eval --parts R1,R1b,R2,R3,R3full,R4,R4b`; `python scripts/baselines/r6_energy.py`; `python -I scripts/baselines/retune_v2.py eval`;
`python scripts/baselines/baseline_clock.py rows|reprice`; `pytest -q tests/hw`. Raw: sim/out/hw/baselines_v2/ (gitignored; cloud
return checksums 00_admin/cloud_cpu/offload/return/baselines_v2.sha256).

Known gaps: section 6. The R3full PASS must not be cited.

## Internal review verdict (17 Nov 2026, independent reviewer; HEAD fce3e6f, results commit ea6dba9)
Checks run: prereg order vs raw outputs; R6 evaluator code and r6_result.json; HyCiM paper text (arXiv 2410.14111v1 Sec. 3.1, 3.4, 4.3);
clean HEAD worktree pytest of test_cost_rule_all_tables / test_b1_native / test_baselines_v2. The pytest run could not execute
locally: `numba` is not installed in any local Python (fujitsu_da.py:237 import fails at collection), and installing it is outside
review scope. No test result below is re-verified by this review.

| Item | Verdict | Evidence |
|---|---|---|
| A1 | FAIL (honest) | B1_yin is faithful in design (one proposal of m in {1,2,3} bits per iteration, MESA v2, own clock). Fig. S7 not reproduced in R1 or R1b, both registered. The full outcome ("reproduce at least one published figure") is not met. It is stated as a gap, not hidden |
| A2 | PASS (code read; tests not re-run) | MesaV2Unit epoch cooling; K >= epoch is structural; regression tests are named in the internal review |
| A3 | FAIL (honest) | R2 Fig. 2 PASS. Scaling: R3 FAIL, and R3full is correctly flagged invalid (the TTS80 of 5.98e6 / 1.20e7 is the Jeffreys zero-success floor at L* = 25 n, linear in n by construction). The bimodal beta of 0.0030 is labelled post hoc, as it must be. Gaussian is n.e. No registered scaling reproduction exists |
| A4 | PASS | B3 v2 solves colouring (R6 PASS). The diagnosis (search space, not encoding) is supported by B3-10 |
| A5 | FAIL | The paper defines an iteration as one proposal: "During each SA iteration, the SA logic generates an input variable configuration" (Sec. 3.1; again in Sec. 3.4 / Fig. 6b). The 99.43 % depends on reading "iteration" as a sweep of 100 proposals, which the text contradicts. Under the paper's own definition the result is 16.5 % (not reproduced). The runs design was also reduced (100 init x 10 runs vs 1000 x 100). This also conflicts with B1, where the same group's "iteration" is read as one proposal |
| A6 | PASS | Same 8-config grid shape, TUNE split, seeds and selector for every arm (prereg s.5, bb57453 extends it to B1_yin). Asymmetry: B3 v2's secondary knob reaches T_end^2/T_start, while ours kc2 has no such knob. It favours B3, so R6 is conservative for ours |
| A7 | PASS | B3 lane P&R at 2.687 ns vs ours 2.409 ns. B1 priced as lane + tile adder cycles. The Stage 4 reprice is recorded |
| A8 | FAIL (not yet shown) | energy_table_measured_v2.csv is now tracked at HEAD, so the measured_v2 cases should run. No run is recorded, sections 4 and 6 still say "skipped", and this review could not run them (no numba) |

Prereg discipline: PASS. d1012b8 (16 Nov 23:29 UTC) precedes every scored output (R1 from 23:40). Amendment bb57453 (17 Nov 14:44) precedes the
governed runs (R1b 19:00-19:03, R3x 19:08-20:26, B1_yin tune/test 19:02-20:28; job pin 5344d30). Every R1b record embeds
amend1_sha256 cb7dd1ed..., which matches the committed amendment file.

R6 fairness: same Stage 4 TEST instances, seeds (p7.SEED_TAG, p7.test_seeds) and budgets (p7.sweeps_of). The success target is identical
(best_E <= 0 for both, retune_v2.py:174, 186). Not done: energy / ETS99 under measured_v2 (r6_result.json has success only). So
"beats ours" is a success-rate claim only.

**Not yet accepted. Fix list:**
1. BASELINES_V2.md section 1 B2-1 and section 2 R4 row; prereg R4 (P4_v2_reproduction.md:68-73): report A5 as *not reproduced under the
   paper's definition of an iteration (16.5 %)*. The 99.43 % should appear only as a reading that the paper text contradicts, with the
   Sec. 3.1 quote. Alternatively, register a new reading with a justification drawn from the paper, then run it.
2. Run `tests/hw/test_cost_rule_all_tables.py` (measured_v2 cases) in an environment that has numba, and record the pass/skip counts.
   Update section 4 (A8 bullet) and section 6 (bullet 4).
3. R6: price B3 v2 and ours Kc2+I11 on p3n240 / p3n480 under measured_v2 (energy per success / ETS99 with CIs) and add the result to section 3.
   Until then, describe R6 as success-rate only.
4. Record in the internal review the exact environment / interpreter used for `pytest -q tests/hw`. A clean checkout cannot run it on this machine.
5. A1 and A3 stay honest FAILs against the target bar. Ask the author to accept them as documented gaps, or to fund the Gaussian run at
   about 500 runs per instance (section 6).

## Response to the internal review fix list (20 Nov 2026)
| Fix | Done | Evidence |
|---|---|---|
| 1 (A5) | R4 relabelled FAIL (16.5 %) by the paper's definition (Sec. 3.1 quote in section 1 B2-1). Re-attempt R4b, registered before running (amendment 2, f12ae71), uses the paper's 1000 x 100 design and Fig. 10 per-initial-state scoring: FAIL, 45.0 %. Diagnosis in section 3b; no faithful fix is identifiable | RESULT P4v2 R4 FAIL, R4b FAIL (`repro_v2.py eval`); raw sim/out/hw/baselines_v2/R4b (40 files, amend2_sha256 in each) |
| 2 (A8) | measured_v2 cost-rule cases run: 12 passed, 0 skipped | swref interpreter; section 4 |
| 3 (R6 energy) | B3 v2 vs ours / B1 priced under MeasuredCostV2, ETS99 with CIs | section 3 energy table; r6_energy_measured_v2.json |
| 4 (environment) | Interpreter and versions recorded; full `tests/hw` suite 538 passed, 0 skipped | Internal review "Interpreter" line |
| 5 (A1/A3) | Kept as honest FAILs and passed to the author (section 6) | section 6 |
| Coordinator: R6 fairness | ours.kc2c arm (amendment 2 C) run (72/72 jobs). It does not change the result: B3 v2 still wins on p3 families (ETS99 3.65 / 8.16) | section 3 fairness table; r6_result.json; r6_energy_measured_v2.json |

## Re-check 1 (internal review, 20 Nov 2026; HEAD 02801c4)
Verified independently:
- Prereg order. f12ae71 (amendment 2) was committed 15:44:36 UTC. The first R4b raw file is from 15:44:50, and every R4b file embeds
  amend2_sha256 67d4beba..., which equals the committed file. The ours.kc2c outputs are from 19:39-19:50.
- Tests. A clean detached worktree at 02801c4 with the swref interpreter gives `pytest -q tests/hw`: **584 passed, 0 failed,
  0 skipped**. The count is above the internal review's 538 because HEAD now also carries other tracks' tests.
- R6 energy. Re-running `scripts/baselines/r6_energy.py` on the raw outputs reproduces r6_energy_measured_v2.json byte for byte.
- The R6 fairness arm (ours.kc2c) gets the same T_final knob. B3 v2 still wins on p3 (ETS99 3.65 / 8.16, with CIs that exclude 1).
  The finding is robust.

| Item | Re-check 1 |
|---|---|
| A1 | Honest FAIL, accepted gap (disclosed in sections 2 and 6 and in the internal review) |
| A2 | PASS (suite passes) |
| A3 | Honest FAIL, accepted gap (R3full flagged invalid; post-hoc beta labelled) |
| A4 | PASS |
| A5 | Honest FAIL under the paper's definition (R4 16.5 %, R4b 45.0 %, both preregistered). The diagnosis is sound, and refusing to tune toward 98.54 % is correct |
| A6 | PASS (fairness arm closes the knob asymmetry) |
| A7 | PASS |
| A8 | PASS (measured_v2 cases now run inside the passing suite) |

Fix list (one item, documentation only):
1. BASELINES_V2.md line 72 still says "success only, energy not compared here". The measured_v2 energy table now shows B3 v2 ahead on
   energy as well. Change that sentence to point to the energy table, so that every summary matches.

**accepted once fix 1 is made.** No re-check is needed for that one-line edit. A1, A3 and A5 stand as fully disclosed honest FAILs.

Re-check 1 close-out: stale line 72 fixed in the commit that adds this line; accepted.
