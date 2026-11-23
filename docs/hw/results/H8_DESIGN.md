# H8 design: full hardware comparison (D1-D8)

Status: design + implementation + smoke. **No H8 compute has run; no result exists.** Prereg `prereg/hw/H8_full.md` is a DRAFT (frozen only by a later commit).
Branch `hw/p4-baselines` (worktree `hw-p5b`). Everything below is stand-in-model cost accounting (ratios only, about x2 absolute uncertainty).

> **Sections 1-9 describe the first issue (pin 4e530a9). Section 11 lists what the internal review's verdict (section 10) changed; where they differ, section 11 and `H8_full.md` rule** (G-set 800 removed, G1000 = G51-54, global Holm verdicts, m = 20 / 26 MDEs, core-only gate, hard-timed set-up and gate, new cost figures).

## 1. What the study answers
Apples to apples, on fresh instances and seeds: where does each machine win, and how far does that scale? Machines: ours (Kc2 + I11 and `none`), B1 (best
parallel-trial arm), B3 (Aramon DA v2), the fairness arm ours.kc2c (hook), with B1_yin as ideal-device context and B2 excluded (QKP-only). Every analog machine runs with
its **chosen mitigation** at nominal variation (ours wv + diff + cal, B1 wv + cal) and on the **ideal device**; B3 is digital. Families: planted 3- / 4-colouring at
120 / 240 / 480 / 960 spins (2040 in the full tier), generated DIMACS-style graphs (queen, mycielski, Kneser: exact chromatic numbers, no download), Max-Cut G-set
800 / 1000 (2000 full). Primary pricing `measured_v2` + mitigation overhead per run; sensitivities listed in the prereg. Statistics: ETS99 with the frozen paired
bootstrap, global Holm over the primary contrasts, power analysis for the seed / instance counts. Ablation ladder re-run with mitigations; variation stress at the design
point with k, C2C-share, drift and unmitigated axes; DSATUR / TabuCol / SA success context and 20x TabuCol solvability.

## 2. Files
| file | role |
|---|---|
| `prereg/hw/H8_full.md` | DRAFT prereg (hypotheses, arms, instances, pricing, statistics, tiers, decision rules, limitations) |
| `scripts/testing/plan_h8.py` | the design as data: arms, fresh instance sets, (instances, seeds) per size and tier, stress axes, run-time model, `power_diff` / `mde` |
| `scripts/testing/h8_instances.py` | planted ladder, queen / mycielski / Kneser generators (+ G-set names); lazy imports so the job generator runs under `python -I` |
| `scripts/testing/gen_jobs_h8.py` | cells -> jobs; `--tsv --tier core|full [--kc2c-addon] [--with-kc2c]`, `--summary` (CPU-h, Rs), `smoke_types()` |
| `scripts/testing/run_h8.py` | job runner (one process per job) and `--smoke-h8` (also reachable as `run_cell.py --smoke-h8`) |
| `scripts/testing/evaluate_h8.py` | the report barrier: cells, scaling, ablation, stress, software, sensitivities, power; asserts every raw file is read |
| `scripts/cloud/h8/{jobs_h8_core,jobs_h8_full,jobs_h8_core_kc2c,jobs_h8_full_kc2c}.tsv` | job lists (7 columns: id, mode, rss, est_min, timeout_min, command, **smoke_command**) |
| `scripts/cloud/h8/{setup_h8,go_h8,collect_h8,build_payload_h8}.sh`, `h8_sched.py` | zero-manual-step set-up, gate + run, collection, payload build, memory-aware scheduler |
| `tests/hw/test_h8.py` | 41 tests (instances, fresh seeds, plan / budget / limits, command resolution, kc2c hook, evaluator end to end on real tiny runs, scheduler) |
Small edits to shared files (additions only): `machines.mapped` (H8 colouring families), `machines.drive_sw` (Max-Cut SA reference; H8 graph dispatch), `plan.FAMILY_ID`
(ids 16-20), `run_cell.py` (`--smoke-h8` delegates). `test_h6`, `test_h7`, `test_testing_runner`, `test_variation_v2` pass with them (300 tests with `test_h8`).

## 3. Design decisions and why
- **Fresh by construction.** Tag 9, inst_index 500+, planted seeds 1101 / 1201 up, G-set instances outside Stage 2 TUNE and TEST; tests recompute disjointness from the plan
  tables and check that all H8 run seeds are distinct (`test_seed_stream_and_instances_are_disjoint...`, `test_planted_seeds_do_not_overlap...`).
- **No tuning in H8.** Frozen selections only (Stage 2, P4_v2); no machine gets extra effort (A6). `ours.kc2c` waits for its own selection.
- **Core vs full are one design.** The full job list contains every core job under the same id (done markers make a resume skip them) plus new ids suffixed `x` (extra seeds /
  instances) and the new cells; the full cost is stated as the exact increment. Chunks are filled to 25 estimated minutes, never more than one run past it; no job is estimated
  over 50 minutes and every timeout is <= 60.
- **Mitigation accounting.** Nominal runs go through `PerturbedCimV2` (VARIATION_V2); each record carries `variation_v2.mitigation_cost`. The evaluator RE-PRICES the final counters
  with `MeasuredCostV2` and recomputes the overhead on that table (no canonical-table leakage into the primary), then scales cumulative energy / time, adds the area and charges the
  one-time programming + calibration energy to every run (sensitivity `no_once_cost` drops it).
- **Power.** The success-difference MDE of each size / tier is computed from the stated variance model and printed in the report; sizes 960 / 2040 resolve only large gaps, and the design says so.
- **Memory.** A mitigated run holds (32 x cells) float64 programming arrays: 5.0 GB peak for ours at 960 spins (measured), up to 51 GB declared for the largest graph at 2048 lanes.
  The scheduler admits by declared RSS; the smoke gate measures peak RSS of every job type in its own process and fails if it exceeds the declaration.

## 4. Budget (Rs 64.28 / h, 32 vCPU, 15 min set-up, smoke gate 9 min, tail factor 1.15)
Measured per-run seconds: Stage 4 cloud wall times (ours Kc2+I11 1.8 s @240 spins / 150 sweeps, 10.2 s @480 / 300; B1 7.2 / 52 s; B3 1.5 / 6.8 s), power law in lanes (a test checks the model
reproduces them within 12 %), mitigation factors 1.45 / 1.55 (VARIATION_V2 wall times), Max-Cut from `plan.us_per_step`, margin 1.3.
| tier | CPU-h (jobs) | Rs | wall h | longest job |
|---|---|---|---|---|
| CORE (without ours.kc2c) | 80.4 (449) | **211** | 3.3 | 25 min |
| CORE + kc2c add-on | 88.7 (496) | 231 | 3.6 | 25 min |
| FULL increment over CORE | +102.1 (+426) | +236 | +3.7 | 48 min |
| FULL increment with kc2c | +112.8 (+486) | +261 | +4.1 | 48 min |
| FULL total | 182.4 / 201.5 with kc2c | 447 / 491 | 7.0 / 7.6 | 48 min |
CPU-h by phase (core): main 69.3, stress 8.8, ablation 2.0, software + context + reference about 0.2; B1_best is 56 of the 80 CPU-h (ours Kc2+I11 9.9, ours none 10.6, B3 1.8). Hard compute cap 245 min (about Rs 289 all-in) so the cap cannot
be exceeded; `go_h8.sh` stops new jobs at 225 min. The estimate carries about +-30 % model risk (no measured run at 960 spins mitigated; 2040 spins and Max-Cut at 1000 spins extrapolated); the 31 % reserve to Rs 300 covers it.
The FULL increment by cell: 2040-spin planted 27.2 CPU-h (trend only: 4 x 2 runs, MDE 0.71), generated graphs 37.3 (4 extra graphs plus 12 instead of 8 seeds), p3 / p4 960 spins 19.0, 480 spins 5.8, 120 / 240 spins 3.6, Max-Cut 9.4 (G2000 4.8, G1000 1.7, G800 2.9).

## 5. Smoke and test status (local, via the local job queue, 17-20 Nov 2026)
- `pytest tests/hw/test_h8.py test_h7.py test_testing_runner.py test_variation_v2.py test_h6.py`: **300 passed**.
- `run_h8.py --smoke-h8`: every job type of the full tier (about 100: coverage types + complete rectangles of p3n240, the generated graphs and G-set 800 for every arm) in its own process via its own smoke
  command at 1 sweep, peak RSS against the declaration, then the real `evaluate_h8` barrier on the smoke dir with the assertion that every raw file is read and the report is non-empty. See the last section for the
  recorded result. Types whose declared RSS does not fit the local 9.7 GB WSL machine (mitigated ours / B1 at 2048 lanes and the largest graphs, declared 7.8-51.6 GB) are SKIPPED with a message locally and run by the cloud gate (`--smoke-all`, 128 GB).
  Their unmitigated (ideal) 2040-spin variants ran locally, and the mitigated path ran at 960 spins.
- Payload clean-unpack: see the last section.

## 6. Internal review (checklist D1-D8 -> evidence)
| item | required | what was built | evidence to check |
|---|---|---|---|
| D1 fresh, pre-registered, frozen | fresh instances / seeds; prereg frozen by commit before data | tag 9, inst_index 500+, seeds 1101+ / 1201+, unused G-set graphs, generated graphs; prereg DRAFT with a launch guard | `H8_full.md` section 3; `test_seed_stream_and_instances_are_disjoint...`, `test_planted_seeds_do_not_overlap...`; `go_h8.sh` REFUSES a DRAFT prereg and a TSV that differs from a fresh `gen_jobs_h8.py`. **Open: the freeze commit.** |
| D2 scale ladder 120 -> 960 -> 2048+ with enough seeds | ladder, budgets from pilots on tuning-only seeds, power | 120 / 240 / 480 / 960 core, 2040 spins (2048 lanes) and G-set 2000 in full; budget 150 x N / 240 (cap 600), the H7 rule validated by the Stage 4 pilots (16 Nov, TUNE seeds 851 / 951); `power_table()` | `plan_h8.INST_SEEDS`, `mde()`, prereg section 3 / 5, report `## Power`. **Gap: no new pilot at 960 / 2040 on tune seeds was run (budget rule inherited); 2040 is trend-only (MDE 0.71) and priced by extrapolation beyond N = 1024.** |
| D3 ablation with mitigations | I7 / I10 / I11 / I3 / I5 and restart arms re-run with the chosen stack | ladder L_none, L_da, L_mesa, L_kc2, L_kc2_i11, L_kc2_i7v2_i11, L_kc2_i7v2i10_i11, L_kc2_i11_i5 on p3n240 / p4n240 (ideal + nominal) and G800 (nominal); I3 recorded not applicable (knapsack-only) | `plan_h8.LADDER_ARMS`, `gen_jobs_h8.cells` (abl), report `## Ablation ladder`; smoke ran every rung through the mitigated path |
| D4 Max-Cut re-test under measured_v2 | L2 under the pipelined pricing | G-set 800 / 1000 (2000 full) for every machine, primary `MeasuredCostV2` + per-run mitigation overhead, sensitivities incl. lane-path clock and ungated generators; verdict flips flagged | `evaluate_h8.SENSITIVITIES`, report `## Sensitivities`; Max-Cut L2 is `ours_none vs B3_v2` and `ours_kc2_i11 vs ours_none` in cells `maxcut800 / maxcut1000`. **Note: the Stage 4 B1 contrast is ours_none vs B1_best (not in the registered H8 list); add it if the checker wants L2 against B1.** |
| D5 more DIMACS families | expand with scaled budgets | queen 5-10, mycielski 4-7, Kneser (5 graphs), budgets max(150, 150 x spins / 240) capped 600; download-only DIMACS files excluded for licence | `h8_instances.GRAPHS`, `test_dimacs_style_graph_sizes_match_known_headers`, `test_kneser_...`; per-graph success table in the report |
| D6 TabuCol / software context | time / energy-to-solution context honestly, software energy only if defensible | DSATUR, TabuCol, SA success + CPU s per run (labelled not a hardware cost); 20x TabuCol solvability; **no software energy** (not defensible) | report `## Software context`; prereg H8-F |
| D7 evaluator / runner defects | smoke through the real report, every job's output read, barriers | `--smoke-h8` runs every job type via its own smoke command, measures RSS, then the REAL barrier; `evaluate_h8.main` asserts `n_files_read == n_files` and a non-empty report; the scheduler runs the barrier only if every earlier row has a done marker; out dir is explicit per job; tests inject a stray file and an empty dir | `run_h8.smoke_h8`, `test_main_fails_when_a_raw_file_is_not_read...`, `test_main_fails_on_an_empty_raw_dir`, `test_scheduler_does_not_run_the_barrier...`, `test_every_command_resolves...` |
| D8 zero-manual-step cloud set-up | verilator, qubo, env, VERILATOR_BIN, clean unpack | `setup_h8.sh`: apt basics, Miniforge, pinned `swref` (versions of `payload/setup.sh`), `eda` env with Verilator 5.050, repo from the bundle at the pin, G-set / qkp / d5c / qubo-bridge data, `env_h8.sh` exporting PATH, `VERILATOR_BIN`, `HW_RTL_ROOT`; version assertions + numba JIT check; `go_h8.sh` chains set-up -> gate (tests + `--smoke-all`) -> prereg / TSV guards -> scheduler -> collection | clean-unpack result in the last section; `build_payload_h8.sh`; **not executed on a real cloud box (no billed run authorised); Miniforge / conda network steps are exercised only by `SETUP_OFFLINE=1` locally** |
Open review questions: (1) is the global Holm family (28 primary contrasts at nominal) the right one, given the per-cell Holm also reported; (2) is "restored" margin -0.10 acceptable; (3) should B1 be included in the ablation (it has none)?

## 7. GPU-port estimate (dominant kernel)
Profile of one 240-spin run (cProfile, local): the time is the per-step Python / NumPy loop of the golden machine, not arithmetic: ours `tim_golden.Machine.step` costs about 100 us per step (3.6 s for 36000 steps), almost all NumPy call overhead of many small array operations (`fastcim._sums`, `cim_field._adc` + `np.clip`, checksum, counters), not arithmetic; B1 spends 74 % of its 12 s in the tiled field read (`yin_mesa.field` -> `fastcim.field` -> `cim_field._adc`, 16 tile ADC conversions per step, 576k `_adc` calls for 36k steps). The step is sequential
(each flip changes the field of the next), the parallelism is lanes (128-2048) and the thousands of independent (instance, seed, arm) runs.
1. **Numba-CPU port of the step loop** (golden step, field read + ADC + accept + select + flip / incremental column update + counters, one `@njit` function per machine): effort 1.5-2 weeks incl. bit-exact tests against
   `tim_golden` / the RTL spot check (counters and `restart_cycles` must match), speed-up 15-40 x per core (about 3-8 us per step at 256-1024 lanes). It alone would cut the full tier from about 180 CPU-h to 5-12 CPU-h (Rs 12-30) and is the
   cheapest large win (no new hardware, same environment).
2. **CUDA batch kernel (Numba-CUDA / CuPy) on top**: one thread block per run, one thread per lane, state in shared memory, the step loop inside the kernel (block scan for the select tree, xoshiro per lane in registers, integer
   column sums in shared memory); runs are independent so blocks never synchronise. Effort a further 2-3 weeks (restart units Kc2 / MESA, I11, I7v2 / I10, B1 tiled ADC with per-tile clipping, `PerturbedCimV2` noise injection, per-step counters) plus the same bit-exactness suite.
   Expected 2-5 us per step per block, 50-100 resident blocks on an L4 / A10-class card: 1000-3000 vCPU-equivalents on the large (N >= 512) cells, less on small cells (launch and occupancy limits), i.e. the full tier in
   minutes of GPU time. Cost on a rented GPU (Rs ~100 / h assumed) is dominated by set-up, not compute; the benefit is turnaround and the freedom to run 10 x more seeds (the 960 / 2040 cells then reach a useful MDE).
   Programming of the (32 x cells) arrays in `variation_v2` stays on the CPU (once per run, 5-20 s at 960 spins) unless it too is ported (+1 week); memory is the constraint there, not speed.
Risk: bit-exactness (the counters drive the pricing), RNG stream equality for the same seeds (otherwise results are statistically equivalent but not reproductions of earlier records), and the maintenance cost of a
second implementation. Recommendation: do (1) before any larger study than H8; (2) only if a further 10 x scale-up (more seeds at 960+) is wanted. These are estimates from the profile and code structure, not measurements.

## 8. Open risks
1. Run-time model is extrapolated for mitigated runs at 960 spins and above, for Max-Cut at 1000 spins and for 2040 spins (no measured point); +-30 % cost risk, covered by the reserve in CORE, not guaranteed for FULL.
2. N > 1024 lanes: measured_v2 has blocks only to N = 1024; 2048 is a log-log extrapolation (labelled); a new P&R at N = 2048 would make those cells primary-eligible.
3. The 51.6 GB peak of mitigated ours on the largest graphs (programming arrays) means only 2 such jobs fit on 128 GB; they are tail-latency risk. A bit-exact chunking of `program_cells` (draw the 32 attempts in 4 x 8) would cut the peak 4 x, not done here (VARIATION_V2 is a accepted file).
4. Power: 960 (core MDE 0.42) and 2040 (0.71) cells resolve only large gaps; the largest B3-vs-ours contrasts at 240 / 480 (0.85 vs 0.58, 0.69 vs 0.16) are well inside the MDE.
5. The ablation I5 rung (`ours.kc2.fs.i5_h4g4`) uses the Kc2 config tuned without I5; it is a stated, untuned rung.
6. `ours.kc2c` selection pending; prereg and report carry the PENDING label and the add-on TSVs; nothing else depends on it.
7. The prereg is a DRAFT; launch needs the freeze commit and cost approval (E2 / E3).

## 9. Recorded results of the local checks (20 Nov 2026, pin 191495d + docs)
- Tests: `pytest tests/hw/test_h8.py test_h7.py test_testing_runner.py test_variation_v2.py test_h6.py` -> 300 passed (41 in `test_h8.py`).
- `run_h8.py --smoke-h8` (via the local job queue): 112 job types (coverage types + rectangles of p3n240, generated graphs, G-set 800, every arm incl. the kc2c stub, the ladder, stress, software, context, reference),
  **107 run, 5 skipped for memory (declared 7.8-51.6 GB mitigated ours / B1 jobs at 2048 lanes and the largest graphs; the cloud gate `--smoke-all` runs them), 0 failures, every peak RSS within its declaration**,
  then the real barrier: 107 files read, non-empty report. The 5 skipped types are the only job types not exercised locally; the mitigated path itself ran at 960 spins (5.0 GB peak) and at 1000-node Max-Cut.
- Clean unpack: `build_payload_h8.sh` (29 MB: bundle, data, manifest, both TSV sets, scripts) -> `SETUP_OFFLINE=1 MD_ROOT=<scratch> MD_CONDA=<existing conda> setup_h8.sh` in an empty root: repo and worktree at the pin, data restored,
  version assertions and the numba JIT check passed, `env_h8.sh` written (PATH with the eda env, VERILATOR_BIN, HW_RTL_ROOT); `go_h8.sh core` refuses the DRAFT prereg as designed. Then the REAL scheduler and the REAL barrier in that unpacked tree on five
  real p3n120 core jobs (30 instances x 8 seeds, 150 sweeps) plus `report_h8_core` (all sensitivities): 6 / 6 done, barrier 52 s, a non-empty report (e.g. p3n120 nominal: ours Kc2+I11 vs B3 v2 ETS99 0.77 [0.42, 1.16], inconclusive; Kc2+I11 vs none 0.27, win).
  Not exercised locally (needs a billed cloud box): the apt / Miniforge download / pip / conda-forge Verilator steps of `setup_h8.sh` (they are the pinned commands of the proven `cloud_cpu/payload/setup.sh`) and the full-size gate.
- Timing check of the run-time model on those jobs (local loaded WSL, mapped to the cloud with the 0.71 factor of `plan.CLOUD_OVER_LOCAL`): ours none nominal 600 s -> 426 s vs estimated 420 s; ours Kc2+I11 nominal 462 s -> 328 s vs 300 s; B3 228 s -> 162 s vs 240 s; ours none ideal 380 s -> 270 s vs 300 s. The estimate (with its x1.3 margin) is within -10 % / +10 % of the mapped local timing at 120 spins.

## 10. Internal review verdict (20 Nov 2026, independent; pin 4e530a9)
Re-run: `pytest tests/hw/test_h8.py` 41 passed; TSV integrals recomputed; seed / instance overlap searched across all plan files; scheduler, gate, evaluator Holm path and `power_diff` read.

| item | verdict | evidence |
|---|---|---|
| D1 fresh, frozen | **FAIL** | Planted seeds 1101+/1201+, tag 9, generated graphs and G43-47 / G22-26 are fresh. But the G800 set is exactly Stage 3 (H6): TUNE G9 G20, TEST G8 G10 G17 G19 G21 (`scripts/testing/plan_h6.py:16-17`, `prereg/hw/H6_followup.md:39`, results `daad157`). The claim at `plan_h8.py:30` / `H8_full.md:62` checks only Stage 2; `tests/hw/test_h8.py:77` misses plan_h6. All 21 800-node G-set graphs are now used, so no fresh 800-node set exists. Freeze commit still outstanding. |
| D2 scale ladder + power | PASS (with fix 3) | Ladder 120-960 core, 2040 full trend-only, budgets by the validated H7 rule; gaps stated honestly. `power_diff` uses m = 8 (`plan_h8.py:214`, `H8_full.md:98`) while the primary family is the global Holm over 28 contrasts: core MDE becomes 0.24 / 0.28 / 0.36 / 0.46 (recomputed), not 0.21 / 0.25 / 0.32 / 0.42. |
| D3 ablation with mitigations | PASS | Ladder rungs with chosen stack, I3 n/a stated; smoke ran every rung. Its G800 cell inherits fix 1. |
| D4 Max-Cut under measured_v2 | **FAIL** | Pricing and sensitivities correct, but the 800-node L2 re-test runs on Stage 3 instances (two were Stage 3 tuning instances): not a fresh re-test. |
| D5 more DIMACS families | PASS | queen / mycielski / Kneser from definitions, headers tested, scaled budgets. |
| D6 software context | PASS | Success + CPU s as context; no software energy (defensible). |
| D7 evaluator / runner | **FAIL** | Every-file-read and barrier guards are real and tested. But the evaluator does not implement the prereg's primary rule: `contrast_block` sets `energy` from the per-cell Holm p (`evaluate_h8.py:176-178`); `holm_primary` only stores `holm_p_global` (`:232`) and no verdict or markdown column uses it (`:433-435`), contrary to `H8_full.md:22`. The gate also smokes full-tier types for a core run (fix 4). |
| D8 zero-manual-step set-up | PASS | Clean-unpack + real scheduler/barrier recorded; network steps are the proven payload commands; DRAFT / TSV / kc2c guards present. |

Memory: the 51.6 GB is real, not a leak. It comes from vectorised (32 attempts x level-0 cells) float64 arrays over the dense 9 x 2048^2 crossbar (`variation_v2.py:244-247`, about 9.7 GB per array). That is avoidable by chunking, but it only affects the full tier. Core max declared RSS is 13.8 GB (6 jobs). The scheduler admits jobs by declared RSS within 0.85 x MemTotal and refuses jobs that are too large, so there is no OOM interplay. Core memory-bound wall time is 2.2 h, below the CPU-bound 2.6 h.
Cost: core TSV is 450 rows / 84.2 CPU-h. With x1.15 and set-up + gate that is about Rs 220, and about Rs 270 at +30 %. The compute hard cap of 245 min fits Rs 300 only if set-up and gate are bounded (fix 4). The kc2c hook is sound.

**Not yet accepted. Fix list:**
1. `plan_h8.py:30,47,144`, `H8_full.md:62`: label G800 as reused (Stage 3 TUNE/TEST) and remove it from the H8-A global Holm family and the headline verdicts, or replace it with unused graphs (e.g. G27-31 / G35-39 at 2000 nodes in core). Move the Max-Cut ablation to G1000. Extend `tests/hw/test_h8.py:71-77` to the plan_h6 / plan_h7 sets.
2. `evaluate_h8.py:176-178,220-233,433-435`: add the primary verdict computed with `holm_p_global` (`energy_global`), print it in the report, and apply the section 7 decision rule to it. Add a test in which the per-cell and global verdicts differ.
3. `plan_h8.py:213-214`: set m to the realised global family size (28 core). Update the MDE tables in `H8_full.md` section 3 / section 5 and in the report. State that power refers to the success difference, while the verdict test is the ETS99 bootstrap p.
4. `run_h8.py:220`: the gate's `smoke_types("full")` makes the core run depend on the 5 never-exercised 7.8-51.6 GB full-only types. Smoke the launched tier's types, so core smokes only core types. `go_h8.sh:27-29`: wrap set-up + gate in a wall timeout (e.g. 40 min) so the Rs 300 cap holds overall, not only for the scheduler phase.
Before FULL (not a core blocker): chunk `program_cells` attempts. Accept that this breaks bit-exactness with VARIATION_V2, or keep the RNG order by drawing per attempt.

## 11. Response to the internal review (fixes 1-4; pin = the commit that adds this section)
| fix | change | evidence |
|---|---|---|
| 1 freshness (D1, D4) | The G800 set is gone (all 21 800-node G-set graphs were used by Stage 2, Stage 3 / H6 or the P4.02 calibration). Core Max-Cut = **G51-G54** (1000 nodes, 4 x 6 seeds, never used anywhere), full adds **G27-G31** (2000 nodes, 5 x 2). G22-26 and G43-47 are also dropped (P4.02 calibration used them). The Max-Cut ablation moved to G1000 (first 3 x 4, nominal). The disjointness test now builds the used sets from Stage 2, H6, H7 (+ pilot seeds 851 / 951), the P4.02 `calib_b1.GRAPHS`, P4_v2 `R1X_GRAPHS` and VARIATION_V2 grids, and compares the ACTUAL mixed seeds of all earlier specs (tags 0, 6, 7, 8) with every H8 seed. | `plan_h8.G_CORE_1000 / G_FULL_2000`, `test_instances_are_disjoint_from_every_earlier_stage_including_calibrations`, `test_seed_streams_are_disjoint_from_every_earlier_stage` |
| 2 evaluator (D7) | `holm_primary` now sets the primary `energy` verdict from `holm_p_global` (the per-cell verdict is kept as `energy_cell`; not-evaluable reasons survive). Report columns: Holm p cell / global, energy (primary, global), cell. An incomplete family is flagged INCOMPLETE and carries no headline verdict. Sensitivities re-derive the global verdicts too. | `evaluate_h8.contrast_block / holm_primary / markdown`; `test_primary_verdict_uses_the_global_holm_p_and_differs_from_the_cell_verdict` (cell verdict win, global inconclusive), `test_not_evaluable_survives_global_holm_and_report_prints_both_verdicts` |
| 3 power | `power_diff` uses m = realised global family: **20 in CORE, 26 in FULL** (the 28 of the review counted the removed G800 and the 2040 cells differently; 2 x (8 planted + generated graphs + G1000) = 20; + p3n2040, p4n2040, G2000 = 26). Power refers to the success difference; the verdict test is the ETS99 bootstrap p. To pay for the larger m, core instances were raised where cheap (120: 40 x 8, 240: 36 x 6, 480: 18 x 5; 960 stays 10 x 4: each added 960-spin instance pair costs about 3 CPU-h of B1). | `plan_h8.primary_family_size`, `power_table`, table below |
| 4 gate and cap (D7) | `run_h8.py --smoke-h8 --tier core|full`: the core gate smokes only core job types (the 2040-spin, G2000 and extra-graph types, and their 13.8-51.6 GB peaks, are smoked only by the full gate). `go_h8.sh` hard-times set-up (20 min), tests (10 min), smoke (15 min); scheduler deadline 205 min + 20 min kill window; collection 5 min: **guaranteed ceiling 275 min = Rs 295** and the cost tables now carry it. | `go_h8.sh`, `gen_jobs_h8.worst_case_rs`, `test_core_gate_smokes_only_core_types...`, `test_worst_case_core_cost_is_inside_the_rupee_cap_and_gate_is_hard_timed` |
Found on the way: the first core smoke measured 5.2 GB peak for mitigated ours on G51-54 against 4.6 GB declared (those graphs have more cells than the 800-node ones); the RSS gate failed it as designed and the declaration was raised (C_CELLS maxcut 3.6). The 2000-node G27-31 constant is unmeasured (cloud full gate checks it).

New figures (summary by `gen_jobs_h8.py --summary`):
| tier | CPU-h (jobs) | typical Rs | wall h | note |
|---|---|---|---|---|
| CORE | 80.1 (442) | 211 | 3.3 | scheduler wall 173 min of the 205 min deadline |
| CORE + kc2c | 88.3 (486) | 230 | 3.6 | 190 min of 205 |
| CORE guaranteed ceiling | - | **295** | 4.6 | all phases hard-timed |
| FULL increment | +110.9 (+450) | +256 | +4.0 | with kc2c +122.4 / +283; own full-types gate |
| FULL total | 191.0 | 467 | 7.3 | with kc2c 210.7 / 512 |
Core MDE of the success difference (80 % power, m = 20): 120 spins 0.20, 240 spins 0.23, 480 spins 0.33, 960 spins 0.45; full (m = 26): 0.18 / 0.20 / 0.28 / 0.38, 2040 spins 0.75 (trend only). Trade-off: the 960-spin core cell still resolves only large gaps; halving that MDE needs about 4 x the 960-spin runs (+25 CPU-h in B1 alone), which does not fit the Rs 295 ceiling.
Not changed: D8 / D5 / D6 / D2 rows; the full-tier memory chunking of `program_cells` remains a pre-FULL item.
Re-run after the fixes (local, the local job queue): `pytest test_h8 test_h7 test_testing_runner test_variation_v2 test_h6` 305 passed; `run_h8.py --smoke-h8 --tier core --with-kc2c`: 104 core types, 101 run, **0 failures**, 3 skipped locally (the 13.8 GB mitigated dimacs types; the cloud gate runs them with `--smoke-all`), every peak RSS within its declaration, barrier: 101 files read, non-empty report (global-Holm columns present; the smoke family is incomplete and flagged as such).

## 12. Internal re-check 1 (20 Nov 2026, pin 29019ce)
- Fix 1 (D1/D4): G800 removed. Core Max-Cut is G51-54; full adds G27-31. No plan file outside H8 names any of them (grep). The ablation runs on G1000, and the disjointness test now covers every earlier stage. **PASS.**
- Fix 2 (D7): `holm_primary` sets the PRIMARY `energy` from the global Holm p (`evaluate_h8.py:238`). The per-cell verdict is kept as `energy_cell` (`:186`), and the report prints the global p (`:449`). **PASS.**
- Fix 3 (D2): m is correct. Core main has 10 families (p3/p4 x 4 sizes, dimacs8, maxcut G1000) x 2 contrasts = 20. Full adds p3/p4 2040 and G2000, giving 13 x 2 = 26. My 28 was counted on the pre-fix design (two Max-Cut groups plus a miscount), so it is superseded. **PASS.**
- Fix 4: the gate smokes the launched tier only (`run_h8.py:223`, `--tier`). Set-up, tests and smoke each have a wall timeout (`go_h8.sh:14,27,28`), and a failure exits 2/3 before `h8_sched.py` starts. The 3 core types at 13.8 GB that were not smoked locally therefore run first in the cloud gate. If they fail, the loss is limited to set-up plus gate (about Rs 40) and no main compute is billed. Acceptable. **PASS.**
- `pytest tests/hw/test_h8.py`: 46 passed (re-run here).
D1-D8: all PASS. The prereg freeze commit and cost approval remain open. **Accepted.**

## 12. 16-vCPU profile and the ours.kc2c integration (20 Nov 2026, after 02801c4)
32 vCPU boxes are unavailable; `go_h8.sh <tier> --profile 16` (or `H8_PROFILE=16`) targets 16 vCPU / 64 GB at Rs 32.14 / h. The default profile 32 is unchanged (its numbers are asserted equal in `test_profile_16_...`).
- **Profile 16:** 16 slots, admission budget 60 GB of declared RSS (`h8_sched.py --slots 16 --mem-gb 60`; a 13.8 GB mitigated job therefore runs at most 4 at a time, tested), core scheduler deadline 450 min (kill at 470), set-up 20 + gate 25 + 470 + collection 5 = **520 min, guaranteed ceiling Rs 279**.
- **Launch guard:** `h8_sched.py --plan` simulates the scheduler (file order, first fit under slots and declared RSS) from the TSV's estimated minutes; `go_h8.sh` refuses to start (exit 4) if the simulated makespan exceeds the deadline, so a tier that cannot complete is never billed.
- **ours.kc2c integrated.** The retune_v2 selection (commit 02801c4) sits in `baselines_v2/tuned.json` under the tune key `ours.kc2.i10` with cid `kc2c_p90_5_t0.5` (tfinal 0.5) for colouring and Max-Cut; `plan_h8._kc2c_selected` accepts that key (only with a `kc2c_*` cid and a tfinal, never the plain Stage 2 Kc2 config). `kc2c_ready()` is now true, so `jobs_h8_core.tsv` / `jobs_h8_full.tsv` contain the arm (core +44 jobs, +8.2 CPU-h); the add-on TSVs remain for reuse. It fits under both ceilings.
- **Bug found by the smoke:** with partial data (a rectangle where no registered contrast has both arms) the evaluator raised `KeyError: 'arms'`; fixed (empty blocks are skipped) with a test.

| core tier (with kc2c) | CPU-h | jobs | typical Rs | wall h typical | simulated scheduler makespan | deadline | guaranteed ceiling |
|---|---|---|---|---|---|---|---|
| profile 32 (32 vCPU, Rs 64.28/h) | 88.3 | 486 | 230 | 3.6 | 180 min | 205 min | 275 min = **Rs 295** |
| profile 16 (16 vCPU, Rs 32.14/h) | 88.3 | 486 | 217 | 6.7 | 347 min | 450 min | 520 min = **Rs 279** |
Full increment: +122.4 CPU-h (Rs 283 on 32 vCPU / Rs 283 on 16 vCPU: same CPU-h at half the rate and half the parallelism; 8.8 h wall on 16 vCPU), full total Rs 512 / 500 (typical). Profile 16 is slower in wall time (about 6.7 h) but not dearer. Peak declared RSS in the 16 profile simulation is 60.0 GB with 16 jobs running.
Re-run: `pytest test_h8 test_h7 test_testing_runner test_variation_v2 test_h6` 310 passed before the last evaluator fix, `test_h8` 52 passed after it; `run_h8.py --smoke-h8 --tier core` (kc2c real selection): 104 types, 92 run, 12 skipped for local memory (the 6.2 GB Max-Cut and 13.8 GB dimacs mitigated types; the machine had 5.6 GB free), 0 failures, barrier: 92 files read, non-empty. Both schedule plans: `PLAN slots=32 ... 180 min FITS`, `PLAN slots=16 budget=60 GB ... 347 min FITS`.

## 13. Internal re-check 2 (20 Nov 2026, pin 307780b; changes only)
- **ours.kc2c mapping: safe and correct.** `_kc2c_selected` (`plan_h8.py:106-118`) reads only the baselines_v2 tuned.json. It accepts the entry only if `cid` starts with `kc2c_` and a `tfinal` is present. The live file holds `kc2c_p90_5_t0.5`, tfinal 0.5, for both colouring and Max-Cut. `ours_kc2_i11` reads `s2:ours.kc2.i10.i11` from the Stage 2 file, so the shared key name cannot leak into the primary arm. The smoke stub is env-gated (`H8_KC2C_SMOKE_STUB`, set only by `--smoke-h8`) and is tagged `cid smoke_stub`.
- **Ceiling: guaranteed.** The hard kill at deadline + 20 min (`go_h8.sh:36`) and the wall timeouts on set-up (20 min), tests (10 min) and smoke (15 min) bound the run: 45 + 470 min + collection is about 520 min, roughly Rs 279 at Rs 32.14/h. The plan guard (`go_h8.sh:39`, exit 4) refuses a schedule whose simulated makespan (347 min) exceeds the deadline (450 min).
- **12 unsmoked types: acceptable.** A failure in the cloud gate exits 3 before `h8_sched.py` starts. The worst-case loss is set-up plus gate, at most 45 min, about Rs 24 on the 16-vCPU profile.
- **Memory admission: one fix.** `--mem-gb 60` (`go_h8.sh:13`) is absolute. On a box sold as "64 GB" the kernel often reports a MemTotal of about 61-62 GiB, which leaves under about 2 GB for the OS and page cache when four 13.8 GB peaks coincide. An OOM kill there fails a job, and the barrier then stops the report.
  Fix: in `h8_sched.py:74`, set budget = min(mem_gb, MemTotal - 4 GB) when `--mem-gb` is given, and log it. Re-run the plan guard with that budget.
`pytest tests/hw/test_h8.py`: 52 tests per the authors (not re-run here; the change is a light one).
**Verdict: accepted once the one-line admission cap fix lands. The verdict is unchanged for the 32-vCPU profile.**

Re-check 2 close-out: MemTotal cap applied in the commit that adds this line; per the review, accepted for both profiles. (Plan at assumed MemTotal 61 GiB, budget 57 GB: makespan 356 min vs 450 deadline, FITS; Rs 279 ceiling unchanged.)
