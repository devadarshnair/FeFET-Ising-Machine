# timing study v2: pipelined select tree, pipelined restart unit, clock-gated generators, measured_v2

Branch `hw/p4-baselines` (worktree `hw-p5b`), RTL also on `hw/p3-rtl` (worktree `hw-p3`, `rtl/` now byte-identical to `hw-p5b`). Flow: Yosys 0.69 + ABC, OpenSTA 3.1, OpenROAD 2.0
(conda env `openroad`), Nangate45 / FreePDK45 typical corner, global route, as in `TIMING_AREA_V1.md` (same SDC: ports stand for flops, input
delay 0.10 ns, output delay 0.05 ns). Reported delays are post-route **data arrival times**, the timing study v1 convention. All numbers are stand-in
cost-model numbers (ratios only; absolute values about x2 uncertain); typical corner, no detailed route, one P&R run per configuration.

This is the third issue of the document. The first internal review verdict ("Internal review verdict" at the end) was NOT accepted on C3 with four fixes ("Second issue"); re-check 2 passed C1-C6 and asked for three more
("Third issue": restart cycles priced and verified cycle-exact, N = 1024 P&R variance bounded, Max-Cut L2 labelled tie / fragile); re-check 3 asked for the full-unit restart seeds and the L3_laneclk re-pricing (section 4b, F6.1). The "Summary", "Second issue", "Third issue", sections 4b / 5 / 7 and the internal review reflect the current state.

## Summary (checklist C1-C6, second issue)

| item | result |
|---|---|
| C1 pipelined tree | `select_tree_pipe` (cuts after chosen adder levels / walk steps, always after the multiply), `SEL_LAT` cycles in state SEL; the selected spin is identical, only cycles change. Bit-exact: golden `CycleCfg(sel_lat)`, `tb_select_pipe` (1494 checks), top-level runs, Verilator smoke, `rtl_spotcheck --sel off/mid/max`. N = 1024 path 9.15 ns -> 3.06 ns (SEL_LAT 3, shortest QUBO step 18.4 ns vs 36.6 ns) or 2.45 ns at the lane-path clock (SEL_LAT 5, 19.6 ns). |
| C2 Kc2-only unit and restart pipelining | `restart_unit MESA = 0` measured at N = 64 / 128 / 256 / 512 / 1024; area is only 3-6 % below the full unit (the Fisher-Yates permutation table is the unit). The restart paths were pipelined (kick in six steps, two-stage permutation read, two-stage MESA encoder, two-stage permutation init): at N <= 512 both units now run at 1.6-1.9 ns post-route (first issue 3.27 / 7.28 ns at N = 512), at N = 1024 at 2.18 ns (full) and 2.80 ns (Kc2-only; 30 % floorplan utilisation, see section 2 and gap 2; first issue 3.83 / 14.08 ns). With the primary select tree (3.06 ns at N = 1024) no restart unit sets a clock; B1's MESA unit is treated by the same rule as ours. |
| C3 clock gating and idle power | Lane and selection generators are clock-gated in the RTL (`clk_gate`, `RNG_CG = 1`, library `CLKGATETST_X1` measured). Gate-level power re-measured with the gated netlists (4 gated + 8 free-running runs, 0 mismatches against the RTL): gated generators cost 1.33 pJ per advance (ungated 3.3-5.3 pJ per step), nothing under I11, the two clock gates 64-80 fJ per step. The idle energy of every block was measured and the primary measured_v2 charges it to every machine (ours, B1, B3) under one rule (lanes, clock gates, select tree, controller, restart unit); free-running generators are the sensitivity `L5_ungated`. |
| C4 measured N | 64 / 128 / 256 / 512 / 1024 measured for every block; no interpolation at any size the stages use. |
| C5 analog model | `analog_model.py`: every analog parameter with low / nominal / high, 15 corners x 2 stages re-priced on the final primary pricing; the array settle is priced in ns on request (`L4_settle20`). |
| C6 lint / SPEC | `lint.sh` clean in four builds (v0, pipelined tree, Kc2-only unit, ungated generators); SPEC_v0.md documents offsets 22-32, `SEL_*`, `RS_MESA`, `RNG_CG`, `SEL_LAT`, cycle formulas (second-issue additions: `RNG_CG`, the restart FSM). |

Headline for the claims (primary measured_v2 = L3_v2, ETS99 ratio ours / B1_best):

* **Max-Cut L2 (ours_none, nominal ADC) vs B1_best: 1.090 loss (v1) -> 0.943 at the median N = 1024 clock (0.960 at the worst clock): a tie / fragile, not a win.** It is above 1 with the baselines on the lane-path clock (1.057) and with free-running lane generators (1.105), a tie with a 20 ns analog settle (0.984), and its registered verdict flips in 8 of the 17 analog / sensitivity rows. With the rule-B tree the Kc2-only restart unit binds the clock of the Kc2 arms (re-check 3): Max-Cut L2 (an arm-none contrast, no restart unit) is 0.924 at the median and 0.926 at the worst clock (L3_laneclk / L3_laneclk_worst), the Max-Cut Kc2 + I11 loss 5.13 / 5.27, and no Stage 4 verdict changes. The full-scale-ADC contrast stays below 1 in every column (0.707 primary). The Max-Cut Kc2 + I11 arm stays a loss (5.06).
* **Colouring L1 (Stage 3)** stays a win (col3p 0.247, col4p 0.005; area win). **Stage 4**: every L1 contrast keeps its registered verdict (inconclusive on p3n240 0.495 / p3n480 0.878 / p4n480 0.316, p4n240 not evaluable) and the scale verdict stays **None**; DIMACS Kc2 + I11 stays a win (0.003) with the area loss (1.10); DIMACS ours_none vs B1_best is a loss (1.169); restart cycles priced and the N = 1024 clock at the median / worst of 7 P&R runs change none of these verdicts.
* With ungated generators (what the RTL had) the I11 advantage is smaller (p3n240 0.519) but no registered verdict of Stage 4 changes. The headline conclusion that is fragile is Max-Cut L2: below 1 only with the clock-gated generators now in the RTL and with the pipelined-tree clock; labelled tie / fragile.

## Second issue: what changed after the first internal review verdict

The first verdict (section "Internal review verdict" at the end) gave C1 / C2 / C4 / C5 / C6 PASS and C3 FAIL with four fixes. All four were done; nothing below relies on the first issue's C3 numbers.

| fix | what was done | evidence |
|---|---|---|
| 1. Gate the idle lane generators, re-measure, charge the remaining idle energy to every machine | RTL: `clk_gate.v` (clock gate, ICG model), `xoshiro128ss GATED = 1`, `tim_top` parameter `RNG_CG` (default 1): one gate for all lane generators (seeding shift, or `acc_ld` with `lane_adv`; I11 never), one for the selection generator (seeding shift, `sel_ld`, restart draw). `RNG_CG = 0` keeps the v0 structure. Gate-level: the gated xoshiro netlist (no enable multiplexer) and the library clock gate `CLKGATETST_X1` (`tt_icg`) were synthesised, the gate-level runs repeated with the gated netlists (8 + 4 runs, 0 mismatches against the RTL, clock-gate netlists included). Idle (quiet-clock) energy of every block was measured. Cost model: `MeasuredCostV2(idle_charge=True, gen_gated=True)` is the primary: ONE rule charges every cycle of every machine (ours, B1, B3) the idle energy of its lanes, the two clock gates, the select tree and controller (machines with the tree) and the restart unit (machines with one). Ungated generators are the sensitivity `L5_ungated`. Stages 3 and 4 re-priced. | section 6; `docs/hw/results/timing_v2/gl_power_summary.json`, `h{6,7}_L3_v2.*`, `h{6,7}_L5_ungated.*`; tests `test_idle_energy_is_charged_to_every_machine_under_one_rule`, `test_ungated_generators_cost_every_lane_every_cycle`, `test_idle_charge_can_be_switched_off_and_restart_unit_idle_is_charged`; RTL runs `maxcut16_i7i10_nocg`, `maxcut16_kc2_nocg` (ungated, same traces) and every other run (gated) |
| 2. Pipeline the 3.83 ns restart path | `restart_unit.v`: Fisher-Yates kick split into six registered steps (R_DRAW multiplier, R_ADD partner index, R_SWP1 / R_SWAP two-stage permutation read, R_RD the two writes, R_FL flip; `remain_q` register keeps the subtractor out of the multiplier path); permutation initialisation (`lane_en[scan]` N:1 multiplexer) registered in two stages; the MESA differing-spin encoder split into R_ENC (per 32-spin group any / first index, registered) and R_CHK (group priority and select). Same draws, same permutation, same flips: traces unchanged. Golden `cycles` never contained restart cycles (they are reported apart as `rs_cycles`), so no golden restart-cycle change exists to be made; `tb_restart` (88,805 checks), `tb_top` (cps checked on every step including the restart cycles), new RTL runs with restarts at N = 64 and 256, and the spot check pass. Three RTL iterations were measured (kick pipeline: 3.83 -> 3.54 ns; + permutation init, `remain_q`, two-stage read: see section 2), the table keeps only the final RTL, the first issue as `restart0` rows. | section 2; `rtl/src/restart_unit.v`; `sim/out/t2e_rtl_tests_long.log`; `tests/hw/test_timing_v2.py::test_v2_block_table_is_consistent` |
| 3. Symmetric treatment of B1's MESA path | One rule in `MeasuredCostV2.at`: the clock of every machine with a restart unit includes that unit as pipelined and measured (ours Kc2: Kc2-only unit; B1 MESA: full unit); `restart_in_clock = False` is the v1 policy. The MESA encoder was pipelined in the same way as the Kc2 kick (fix 2), so both units now fit the select-tree / lane clock where the measurements say so; B1 is no longer exempt. | `MeasuredCostV2.restart_stem`, `at`; `test_restart_unit_is_in_the_clock_of_every_machine_that_has_one`; ladder step L3_clk |
| 4. Re-run everything, port to hw-p3 | `run_rtl_tests.sh --long`, `rtl_spotcheck.py --sel off|mid|max`, `lint.sh`, Verilator smoke re-run on the final RTL in both worktrees; `hw-p3` got the golden `sel_lat` / `gen_tests` changes (`counters.py`, `gen_tests.py`) and, so that both RTL branches verify identically, the H6 `adc_fs` RTL (`cim_field_unit.v`, `tim_top.v`, `tb_cim_field.v`) that only `hw-p5b` had: `rtl/` is byte-identical in both trees, the spot check runs against `hw-p3` through `HW_RTL_ROOT`. | section 1 evidence table; internal review |

## Third issue: what changed after re-check 2

Re-check 2 (end of this document) passed C1-C6 and asked for three more things.

| fix | what was done | evidence |
|---|---|---|
| 1. Price the restart cycles | The golden model now knows the cycles the RTL spends in S_RST per restart (`restart.py` `restart_cycles()`: Kc2 6 per kick + 1; MESA 4 per differing spin + 3) and records them as `restart_cycles` in the counters (kept apart from `cycles`, the per-step state machine). `tb_top` writes the per-step `rs_cycles` (`+rs=`), `check_top.py` and `rtl_spotcheck.py` compare them with the golden model **cycle-exact**: Kc2 61 cycles per restart at L = 10 (all restarts of `maxcut16_kc2`, `qubo64_kc2`, `maxcut16_i7i10`), MESA 11 / 19 / 27 / 35 ... = 4 d + 3 (`maxcut16_mesa`, `qubo64_mesa`: 93 and 86 restarts, every one equal). `MeasuredCostV2.adjust_counters` prices them: exact from `restart_cycles` when the counters have it; for the stored Stage 3 / 4 raw records (recorded before) from the restart count: Kc2 `6 * min(kick_L, n_act - 1) + 1` with `kick_L` = 10 unless the record says otherwise, MESA `4 * (0.5 * n_act) + 3` (the raw records do not keep the Hamming distance: 0.5 is the stated assumption, `L5_mesa0` / `L5_mesa1` bound it). Stage 3 / 4 re-issued offline. | `scripts/golden/restart.py`, `counters.py`, `rtl/tb/tb_top.v`, `check_top.py`; `sim/out/t2j_rtl_tests_long.log` (54/54, "S_RST cycles equal the golden model"); `t2j_spot_*.log` 44/44 x 3 (restart cycles compared in every cell); `hw-p3` 60/60 and 44/44 x 3; tests `test_golden_restart_cycles_follow_the_rtl_fsm_formulas`, `test_restart_cycles_are_priced_per_restart_and_old_raw_records_use_the_stated_rule`; ladder step L3_rc, `L5_mesa0` / `L5_mesa1` |
| 2. Bound the N = 1024 P&R variance | `rtl/pnr/run_timing_v2.sh --pnr-one` and `scripts/hw_timing/t2_seed_runs.sh` re-place and re-route a synthesised block for every (seed, utilisation): `place_pins -random_seed` 1 / 2 / 3, floorplan utilisation 30 % and 60 %. Both pipelined-tree blocks that can set the Max-Cut L2 clock have 3 seeds x 2 utilisations plus their main run. **One rule for every N = 1024 block** (`t2_report.py`): path = median over all its runs, `*_worst` = largest path, area and leakage = median over the same runs; a run is excluded only if its global-route estimate lost more than 1 ns against a post-placement netlist that met timing (routing congestion, not logic; this removes the 60 %-utilisation restart-unit runs, reported in the table). `clock_stat = "median"` (primary) or `"worst"` (`L5_worst`). Max-Cut L2 is priced at the median and at the worst clock. | section 4b, `docs/hw/results/timing_v2/pnr_variance_1024.json`, `sim/out/hw/timing_v1/t2seed/`; `h6_L3_v2.*`, `h6_L5_worst.*` |
| 3. Label Max-Cut L2 honestly | Max-Cut L2 is labelled **tie / fragile** wherever it appears (summary, section 5, internal review): it is below 1 only at the median / worst clock, and not across the stated sensitivities (table below). | summary and section 5 |

Max-Cut L2 (ours_none, nominal ADC) vs B1_best, ETS99 ratio, under every stated sensitivity (primary pricing otherwise):

| pricing | ratio | reading |
|---|---|---|
| median clock (primary L3_v2) | 0.943 | below 1 |
| worst clock of the N = 1024 runs (L5_worst) | 0.960 | below 1 |
| baselines on the lane-path clock (L3_lane) | 1.057 | above 1 (loss) |
| 20 ns analog settle (L4_settle20) | 0.984 | tie (within 2 %) |
| free-running lane generators (L5_ungated) | 1.105 | above 1 (loss) |
| rule-B tree (L3_laneclk), restart units in the clock at their median | 0.924 | below 1 |
| rule-B tree at the worst clock (L3_laneclk_worst: tree 2.51 ns, Kc2-only unit 2.89 ns) | 0.926 | below 1 |

Below 1 at the median and worst clock and with the rule-B tree, a tie with a 20 ns analog settle, a loss with the baselines on the lane-path clock and with ungated generators, and the registered energy verdict flips in 8 of the 17 analog / sensitivity rows of section 7 (win -> tie or loss): **the Max-Cut L2 comparison is a tie / fragile, not a win**.

## 1. Pipelined select tree (C1)

**Why the selection is unchanged.** In tim_ctrl state ACC registers `acc_q`, SEL loads `sel_valid / sel_idx / nacc` from the select tree and advances the
selection generator once, RD and UPD follow. `acc_q` changes only in ACC and the selection generator only at the SEL load, so during SEL the tree inputs
(`acc_q`, `r16`) are constant. A pipelined tree can therefore be plain registers with no valid / ready handshake: state SEL is held for `SEL_LAT` cycles and
`sel_ld` (the load of the result registers and the generator advance) fires in the last one. The selected spin of every step is bit-identical to the
single-cycle tree; only the cycles per step change (QUBO `3 + SEL_LAT`, knapsack `6 + SEL_LAT + 2*SEARCH_LAT`). This is a latency parameter, not an
overlapped pipeline: an overlapped (stale-state) pipeline would pick other spins and is not what is built.

**Structure** (`rtl/src/select_tree_pipe.v`, parameters `ADD_CUT`, `WALK_CUT`, instantiated by `tim_top` when `SEL_PIPE = 1`). Operations in order: adder levels
1..LOG2N (level LOG2N is the root count), one multiply `(r16 * count) >> 16`, walk steps 0..LOG2N-1 (root first). A register is placed after adder level k if
`ADD_CUT[k-1]`, always after the multiply, after walk step j if `WALK_CUT[j]` (j <= LOG2N-2). `SEL_LAT = 2 + popcount(ADD_CUT) + popcount(WALK_CUT)`. Node widths
are exact (`LOG2N - depth + 1` bits), every adder level keeps a register copy for the later walk steps. Default `SEL_PIPE = 0` (the v0 tree, `SEL_LAT = 1`, netlist
unchanged).

**Equivalence evidence**

| check | command | result |
|---|---|---|
| pipelined tree = single-cycle tree, 9 cut masks x N = 16 / 64 / 256, 166 patterns each | `scripts/run_rtl_tests.sh --only tb_select_pipe` (`rtl/tb/tb_select_pipe.v`) | PASS 1494 checks |
| golden cycle model | `tests/hw/test_timing_v2.py::test_selection_latency_changes_only_cycles` | trace equal, `cycles` + 20*(lat-1), every other counter equal (lat 2, 5, 9) |
| top level, Icarus, bit-exact trace + per-step activity (incl. `cycles`) vs golden | `scripts/run_rtl_tests.sh --long` (`sim/out/t2e_rtl_tests_long.log`, final RTL) | 54 tests, 54 pass; `maxcut16_i7i10_sl` (8 cycles/step), `qubo16_i10skip_sl` (5), `qubo64_cim_sl` (11), `maxcut16_sl2` (5), `knap16_sl` (15), `maxcut16_kc2_nomesa` (4), `maxcut16_kc2_nomesa_sl` (12), `lane200_256_sl` (12) PASS |
| top level, Verilator, byte-identical to Icarus | `rtl/verilator/smoke.sh` | `sim/out/t2e_vsmoke.log`: 0 failed, 5 skipped (runs this tree's generator does not produce); `hw-p3` (`hw-p3/sim/out/t2e_p3_smoke.log`): 0 failed, 1 skipped |
| Verilator RTL spot check, 3 families x 4 arms x I7/I10 + tweaks + I7v2, both settings | `scripts/rtl_spotcheck.py --sel off` (old behaviour), `--sel mid`, `--sel max` | 44/44 bit-exact in each of the three modes on the final RTL (`sim/out/t2e_spot_{off,mid,max}.log`; SEL_LAT 1 / 5 / 2 + LOG2N + LOG2N-1), and 44/44 x 3 against the `hw-p3` RTL (`HW_RTL_ROOT`, `sim/out/t2e_p3_spot_*.log`) |
| lint | `rtl/verilator/lint.sh` (v0, pipelined tree, Kc2-only unit, ungated generators; N = 8 / 64 / 256; default and -Wall) | LINT OK (`sim/out/t2e_lint.log`) |
| gate-level netlists vs RTL on the representative runs | `scripts/hw_timing/gl_run_all.sh` (section 6) | 12 runs (free-running and gated generators, single-cycle and pipelined tree, library clock gates), 0 mismatches |

Pre-existing failure found and fixed: `b1_maxcut16` did not compile (`tb_top` had no `CIMWB` parameter although `gen_tests.py` passes it); `tb_top` now forwards `CIMWB`.
`run_rtl_tests.sh --long` was 47/48 before the fix and the one failing test passes after it (`sim/out/t2_b1fix.log`). `rtl_spotcheck.py` default (`--sel off`) is the old
behaviour and unchanged.

**Cut-mask search** (`rtl/pnr/run_timing_v2.sh`, `scripts/hw_timing/t2_sweep.py`; synthesis target 2.4 ns, 420 s P&R timeout for hopeless configurations). 165+ configurations
were synthesised and routed; the table keeps the best path per latency (full list in `docs/hw/results/timing_v2/cut_choice.json`). Two rules fixed before the repricing:
(A) the shortest QUBO step time `(3 + SEL_LAT) * max(tree path, lane 2.41, RNG 2.32)`; (B) the fewest SEL cycles with the tree path <= 2.5 ns (the clock stays at the lane path).

| N | configs completed | rule | SEL_LAT | cut masks ADD / WALK (tag) | tree path ns | clock ns | QUBO step ns | tree area um2 |
|---|---|---|---|---|---|---|---|---|
| 64 | 14 | A | 2 | 0 / 0 (`a0_w`) | 2.188 | 2.406 | 12.0 | 2097 |
| 64 | 14 | B | 2 | 0 / 0 (`a0_w`) | 2.188 | 2.406 | 12.0 | 2097 |
| 128 | 22 | A | 2 | 0 / 0 (`a0_w`) | 2.462 | 2.462 | 12.3 | 3717 |
| 128 | 22 | B | 2 | 0 / 0 (`a0_w`) | 2.462 | 2.462 | 12.3 | 3717 |
| 256 | 32 | A | 3 | 0 / 16 (`a0_w4`) | 2.408 | 2.408 | 14.4 | 6629 |
| 256 | 32 | B | 3 | 0 / 8 (`a0_w3`) | 2.432 | 2.432 | 14.6 | 6594 |
| 512 | 38 | A | 3 | 0 / 16 (`a0_w4`) | 2.608 | 2.608 | 15.6 | 12594 |
| 512 | 38 | B | 4 | 0 / 20 (`a0_w2-4`) | 2.457 | 2.457 | 17.2 | 12657 |
| 1024 | 46 | A | 3 | 0 / 32 (`a0_w5`) | 3.059 | 3.059 | 18.4 | 24235 |
| 1024 | 46 | B | 5 | 512 / 72 (`a10_w3-6`) | 2.454 | 2.454 | 19.6 | 23066 |

Best path per latency at N = 1024 (all runs): SEL_LAT 2: 6.00 ns, SEL_LAT 3: 3.06 ns, SEL_LAT 4: 2.73 ns, SEL_LAT 5: 2.45 ns, SEL_LAT 6: 2.24 ns, SEL_LAT 7: 2.31 ns, SEL_LAT 8: 2.42 ns, SEL_LAT 9: 2.41 ns

The single-cycle tree is 3.18 / 4.60 / 5.64 / 7.74 / 9.15 ns at N = 64 / 128 / 256 / 512 / 1024. Area of the pipelined tree is 1.1-1.43x the single-cycle one (24,235 vs 16,935 um2 at
N = 1024, about 3000 more flops for the per-level register copies); the controller with the SEL counter is 3.6k-18.0k um2.

## 2. Restart unit: Kc2-only build and pipelined paths (C2, fix 2)

**Build options.** `restart_unit` has the parameter `MESA` (`RS_MESA` at `tim_top`, default 1 = full unit). `MESA = 0` removes the best-state reload (the differing-spin encoder and the mesa branches of the FSM); stall
counter, epoch best and the Fisher-Yates kick stay. RTL runs `maxcut16_kc2_nomesa` / `_sl` check the Kc2-only build bit-exact against the golden model.

**Pipelining (second issue).** The first issue measured the unit as written: 3.83 ns for the Kc2 kick and 14.08 ns for the MESA encoder at N = 1024. Now (`rtl/src/restart_unit.v`, FSM states widened to 4 bits):

* Fisher-Yates kick, six registered steps per kick (was 3 cycles): R_DRAW `prod_q = rng_o * remain_q` (the generator advances here as before; `remain_q = size - a` is kept in a register updated when `a` changes, so no subtractor sits in front of
  the multiplier) and the group stage of the permutation read of `perm[a]`, R_ADD `jr = a + (prod_q >> 32)` and `pa_q = perm[a]`, R_SWP1 the group stage of `perm[jr]`, R_SWAP `tgt = perm[jr]`, R_RD the two permutation writes (`perm[jr] <= pa_q`, `perm[a] <= tgt`, the coupling-memory read uses `tgt`), R_FL the flip. The permutation read is two-stage: 32 words that share the high index bits are registered (`grp_q`, 32 x LOG2N flops), the low bits pick one.
* MESA reload, per flipped spin R_ENC (per group of 32 spins: any difference and first index, registered) and R_CHK (group priority and select, `low_q` registered), then R_RD, R_FL (was R_CHK, R_RD, R_FL).
* Permutation initialisation (during seeding): `lane_en[scan]` (an N:1 multiplexer) and the index append in two stages; `pinit` must stay high N + 1 cycles (seeding holds it 2(N + 1)).

Same draws, same permutation, same flips and same order, so every state trace is unchanged (all bit-exact tests and the spot check pass); only the cycles spent in S_RST per restart grow. The golden model's `cycles` never contained the S_RST cycles (the testbench reports
them apart as `rs_cycles` and excludes them from the per-step activity comparison), so no golden restart-cycle change exists to be made; `tb_restart` (88,805 checks), `tb_top` (cycles per step checked on every step including `rs_cycles`) and `rtl_spotcheck` pass.
The restart time itself is therefore still not in the priced `cycles` (as in measured_v1): with L = 10 kicks per restart the unit spends about `6 * L + 2` = 62 cycles per restart; a documented gap (section "Known gaps").

| N | full unit (pipelined): path ns / area um2 / leakage uW | Kc2-only unit (pipelined): path ns / area um2 / leakage uW | first issue (unpipelined) full: path ns | first issue Kc2-only: path ns / area um2 |
|---|---|---|---|---|
| 64 | 1.62 / 10233 / 227 | 1.79 / 9896 / 214 | 2.25 | 2.27 / 9401 |
| 128 | 1.65 / 18161 / 420 | 1.79 / 17666 / 401 | 2.81 | 2.33 / 18361 |
| 256 | 1.61 / 35799 / 829 | 1.82 / 34344 / 790 | 3.46 | 2.86 / 39708 |
| 512 | 1.89 / 74303 / 1801 | 1.90 / 70180 / 1691 | 7.28 | 3.27 / 81107 |
| 1024 | 2.18 / 161060 / 3978 | 2.80 / 151950 / 3789 | 14.08 | 3.83 / 177866 |

**Result.** Pipelined, the Kc2-only unit is only 3-6 % smaller than the full unit (the Fisher-Yates permutation table is the unit, the MESA encoder is a few percent); what the pipelining bought is time: at N <= 512 both units run at 1.6-1.9 ns post-route (below the lane path 2.41 ns and the pipelined tree), at N = 1024 at 2.18 ns (full) and 2.80 ns (Kc2-only), against 14.08 / 3.83 ns before. The N = 1024 rows are the floorplan-utilisation-30 % runs: at 60 % the global-route parasitics of the 10,000-flop permutation table were congestion-dominated (full unit 6.59 ns, Kc2-only 3.19 ns, while the post-placement slack was positive at 2.0 ns: +0.02 / +0.23 ns); the same logic gave 2.18 and 2.80 ns at 30 %, which also shows the size of the single-run P&R variance (known gaps). With the primary select tree (3.06 ns at N = 1024, rule A) neither unit sets the clock; under rule B (2.45 ns) the Kc2-only unit would (2.80 ns), which the model takes into account (`restart_in_clock`).
The pipelined restart units are measured at all five sizes and enter the clock of every machine that has one (fix 3, section 5).

## 3. Measured at the sizes used (C4)

Padded sizes in the Stage 3 / Stage 4 records: 128 (colouring Stage 3 and DIMACS), 256 (n240), 512 (n480), 1024 (Max-Cut G-set). measured_v1 had measured 64 / 256 / 1024 and
interpolated 128 and 512. measured_v2 has every one of 64 / 128 / 256 / 512 / 1024 measured for the single-cycle tree, controller, full and Kc2-only restart units (pipelined RTL; the first-issue unpipelined units as `restart0` / `restartk0`) and the pipelined tree, plus the idle energies
(`docs/hw/energy_table_measured_v2_blocks.csv`, 210 rows; per-block outputs `sim/out/hw/timing_v1/{t2,t2sweep}/`, parsed into `docs/hw/results/timing_v2/timing_v2_summary.json`).
`MeasuredCostV2` takes the exact point for these N and log-log interpolates only for any other N. Differences from the v1 interpolation: single-cycle tree 4.60 ns at N = 128
(v1 interpolated 4.2) and 7.74 ns at N = 512 (v1 interpolated 7.2): small.

## 4. measured_v2 tables

* `docs/hw/energy_table_measured_v2.csv`: overlays the same three rows as measured_v1 on the canonical table. `t_clk` = 3.0586 ns (N = 1024, pipelined tree rule A; the per-N clock of every machine
  is set by `MeasuredCostV2`); `a_nand2` and `p_leak_nand2_nw` are unchanged (same lane + RNG blocks, flagged in the row source). measured_v1 files are untouched and `CostModel()` still defaults
  to the canonical table (test pins the hash).
* `docs/hw/energy_table_measured_v2_blocks.csv`: per-N rows `tt_{t,a,p_leak}_{sel,ctrl,restart,restartk,restart0,restartk0}_n*` (single-cycle tree, controller, full and Kc2-only restart unit; `*0` = first issue), `tt_e_idle_*` (idle energy per cycle: lane, free-running generator, clock gates, per-N tree / controller / restart units), `tt_a_rngg`, `tt_a_icg`,
  `tt_*_selp_n*` / `ctrlp` (rule A) and `tt_*_selq_n*` / `ctrlq` (rule B) with `tt_sel_lat{p,q}_n*`, plus the unchanged lane and RNG paths.
* `cost_model.MeasuredCostV2` (additions only; `CostModel.adjust_counters` hook, called by `pricing.price`): switches `pipelined`, `kc2_only`, `charge_select`, `restart_in_clock`, `idle_charge`, `gen_gated`,
  `settle_ns`, `tree` (A or B), `baseline_clock`.

## 4b. N = 1024 place-and-route variance (re-check 2, fix 2)

One synthesised netlist, re-placed and re-routed for seeds 1 / 2 / 3 (`place_pins -random_seed`) at floorplan utilisation 30 % and 60 % (`scripts/hw_timing/t2_seed_runs.sh`), plus the main run(s) of the earlier sections. Rule for every N = 1024 clock-setting block (`t2_report.py`): path = **median** over all runs, `*_worst` row = largest path, area and leakage = median over the same runs; a run is excluded only if the global-route estimate lost more than 1 ns against a post-placement netlist that met timing (congestion, not logic).

| block at N = 1024 | runs (main + seeds, 30 / 60 %) | path ns: all runs (sorted) | median | worst | area um2 median [min, max] | congestion-excluded |
|---|---|---|---|---|---|---|
| pipelined tree, rule A (`a0_w5`) | 7 | 2.98, 3.06, 3.06, 3.15, 3.23, 3.24, 3.53 | 3.147 | 3.526 | 24633 [24155, 24855] | none |
| pipelined tree, rule B (`a10_w3-6`) | 7 | 2.45, 2.45, 2.45, 2.47, 2.50, 2.51, 2.51 | 2.467 | 2.513 | 23089 [22976, 23171] | none |
| full restart unit | 4 | 2.13, 2.14, 2.18, 2.26 | 2.160 | 2.265 | 160914 [160649, 161060] | restart_N1024 |
| Kc2-only restart unit | 4 | 1.77, 2.44, 2.80, 2.89 | 2.620 | 2.889 | 151835 [151640, 151950] | restartk_N1024 |

* The pipelined trees, which set the Max-Cut L2 clock, have the full 3 seeds x 2 utilisations plus the main run: rule A spreads 2.98-3.53 ns (median 3.147 ns used for the clock of every machine at N = 1024, worst 3.526 ns), rule B 2.45-2.51 ns. The primary pricing uses the median rows, `L5_worst` the worst (section 5).
* The restart units were re-run at 30 % utilisation only (the 60 % runs are the congestion artifact of section 2; they are excluded by the rule and listed): **3 seeds each plus the main 30 % run, for both the full unit and the Kc2-only unit** (re-check 3). Kc2-only: 1.77-2.89 ns, median 2.62, worst 2.89; full unit: 2.13-2.26 ns, median 2.16, worst 2.27. The priced rows of Stage 3 / 4 now use these medians (`*_worst` rows for the worst-clock variants); the restart units are faster than the primary tree (median 3.147 ns) but **slower than the rule-B tree (median 2.47 ns): in the sensitivity rows `L3_laneclk` / `L3_laneclk_worst` the Kc2-only unit sets the clock of every arm-Kc2 machine at N = 1024 (2.62 ns median, 2.89 ns worst)**, the full unit that of a B1 MESA machine (2.16 / 2.27 ns, below the tree, so it does not bind).
* Single P&R run at the other sizes (N <= 512): no seed study; the N = 1024 spread (+-8 % around the median for the tree) is the stated bound on single-run numbers.
* Area rule: one stated rule everywhere, area (and leakage) = median over the runs of the block that enter the path statistic; for N <= 512 the single run.

## 5. Offline re-pricing of Stages 3 and 4 (no new runs)

**Validity.** `scripts/hw_timing/reprice_v2.py` re-runs the frozen evaluators (`evaluate_h6`, `evaluate_h7`) on the stored raw counters with the cost model swapped; trajectories, success and
every counter except `cycles` are unchanged because the pipelined tree selects the identical spin (the equivalence evidence in section 1). Re-pricing is **exact for the old-behaviour raw
runs because selection behaviour does not change**: the effect of the latency is `cycles += steps * (SEL_LAT - 1)` per record (`MeasuredCostV2.adjust_counters`). Had pipelining changed which spin is
selected (an overlapped design acting on stale state), the old-behaviour counters would price the wrong machine and only SEL_LAT = 1 re-pricing would be valid; that design is not built. The restart
unit's own cycles and the clock gating do not change the recorded counters either (gating changes energy, not behaviour). Published measured_v1 values are the reference columns (Stage 3: `docs/hw/results/timing_v1/h6_report_measured_v1.json`; Stage 4:
`docs/hw/results/stage4_eval/h7_report.json`). Outputs: `docs/hw/results/timing_v2/h6_<variant>.{json,md}`, `h7_<variant>.{json,md}`.

Increments (each adds one change): L1 = Kc2-only restart unit + N = 512 measured (single-cycle tree); L2 = + pipelined tree (clock and SEL latency, rule A); L3_sel = + select tree and controller
area / leakage charged to every machine; L3_clk = + the restart unit (pipelined, measured) in the clock of every machine that has one (one rule, ours Kc2 and B1 MESA; it does not bind: the restart units are faster than the tree);
**L3_rc = + the restart cycles priced (Kc2 6 per kick + 1, MESA 4 per differing spin + 3, cycle-exact against the RTL); **L3_v2 = + idle clock energy of every machine, one rule, generators clock-gated, N = 1024 clocks at the median of the P&R seed set (primary measured_v2)**; L3_lane = L3_v2 with B1 / B3 on the lane-path clock and no tree (the stated H7 sensitivity); L3_laneclk = rule-B tree with the restart units in the clock at their N = 1024 median (L3_laneclk_worst: worst of the seed set);
L4_settle20 = L3_v2 + 20 ns CiM array settle (priced as ceil(20 / t_clk) cycles per read); L5_ungated = L3_v2 with free-running lane generators (RNG_CG = 0); L5_laneratio = L3_v2 with the lane-logic operation rows x1.27 (annotated / table ratio); L5_worst = L3_v2 with the worst N = 1024 clock; L5_mesa0 / L5_mesa1 = MESA reload spins 0 / all of n_act for the stored raw records.
Cells: ETS99 ratio (ours / B1_best) [95 % CI], registered energy verdict, area ratio.

### Stage 3

| contrast | measured_v1 (published) | L1_kc2only | L2_pipe | L3_sel | L3_clk | L3_rc | L3_v2 | L3_lane | L3_laneclk | L3_laneclk_worst | L4_settle20 | L5_ungated | L5_laneratio | L5_mesa0 | L5_mesa1 | L5_worst |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| maxcut: ours_none_off vs B1_best | 1.090 [1.09, 1.09] loss / area 0.74 | 1.090 [1.09, 1.09] loss / area 0.74 | 0.875 [0.87, 0.87] win / area 0.74 | 0.876 [0.88, 0.88] win / area 0.74 | 0.876 [0.88, 0.88] win / area 0.74 | 0.876 [0.88, 0.88] win / area 0.74 | 0.943 [0.94, 0.94] win / area 0.74 | 1.057 [1.06, 1.06] loss / area 0.74 | 0.924 [0.92, 0.92] win / area 0.74 | 0.926 [0.93, 0.93] win / area 0.74 | 0.984 [0.98, 0.98] tie / area 0.74 | 1.105 [1.10, 1.10] loss / area 0.74 | 0.932 [0.93, 0.93] win / area 0.74 | 0.943 [0.94, 0.94] win / area 0.74 | 0.943 [0.94, 0.94] win / area 0.74 | 0.960 [0.96, 0.96] tie / area 0.74 |
| maxcut: ours_none_fs vs B1_best | 0.800 [0.76, 0.84] win / area 0.74 | 0.800 [0.76, 0.84] win / area 0.74 | 0.652 [0.62, 0.68] win / area 0.74 | 0.653 [0.62, 0.68] win / area 0.74 | 0.653 [0.62, 0.68] win / area 0.74 | 0.653 [0.62, 0.68] win / area 0.74 | 0.707 [0.67, 0.74] win / area 0.74 | 0.792 [0.75, 0.83] win / area 0.74 | 0.704 [0.67, 0.74] win / area 0.74 | 0.706 [0.67, 0.74] win / area 0.74 | 0.777 [0.75, 0.81] win / area 0.74 | 0.835 [0.80, 0.87] win / area 0.74 | 0.702 [0.67, 0.73] win / area 0.74 | 0.707 [0.67, 0.74] win / area 0.74 | 0.707 [0.67, 0.74] win / area 0.74 | 0.720 [0.69, 0.75] win / area 0.74 |
| maxcut: ours_kc2_i11_off vs B1_best | 5.124 [2.32, 8.24] loss / area 0.64 | 5.223 [2.37, 8.40] loss / area 0.65 | 4.310 [1.95, 6.93] loss / area 0.65 | 4.316 [1.96, 6.94] loss / area 0.65 | 4.316 [1.96, 6.94] loss / area 0.65 | 4.323 [1.96, 6.95] loss / area 0.65 | 5.058 [2.29, 8.13] loss / area 0.65 | 5.670 [2.57, 9.11] loss / area 0.65 | 5.125 [2.32, 8.24] loss / area 0.65 | 5.273 [2.39, 8.48] loss / area 0.65 | 5.289 [2.40, 8.50] loss / area 0.65 | 6.088 [2.76, 9.79] loss / area 0.65 | 4.999 [2.27, 8.04] loss / area 0.65 | 5.058 [2.29, 8.13] loss / area 0.65 | 5.058 [2.29, 8.13] loss / area 0.65 | 5.117 [2.32, 8.23] loss / area 0.65 |
| col3p: ours_kc2_i11_off vs B1_best | 0.224 [0.13, 0.34] win / area 0.76 | 0.213 [0.12, 0.33] win / area 0.77 | 0.197 [0.11, 0.30] win / area 0.77 | 0.198 [0.11, 0.31] win / area 0.77 | 0.198 [0.11, 0.31] win / area 0.77 | 0.199 [0.11, 0.31] win / area 0.77 | 0.247 [0.14, 0.38] win / area 0.77 | 0.270 [0.15, 0.42] win / area 0.78 | 0.247 [0.14, 0.38] win / area 0.77 | 0.247 [0.14, 0.38] win / area 0.77 | 0.262 [0.15, 0.40] win / area 0.77 | 0.277 [0.16, 0.43] win / area 0.77 | 0.246 [0.14, 0.38] win / area 0.77 | 0.247 [0.14, 0.38] win / area 0.77 | 0.247 [0.14, 0.38] win / area 0.77 | 0.247 [0.14, 0.38] win / area 0.77 |
| col4p: ours_kc2_i11_off vs B1_best | 0.005 [0.00, 0.01] win / area 0.76 | 0.005 [0.00, 0.01] win / area 0.77 | 0.004 [0.00, 0.01] win / area 0.77 | 0.004 [0.00, 0.01] win / area 0.77 | 0.004 [0.00, 0.01] win / area 0.77 | 0.004 [0.00, 0.01] win / area 0.77 | 0.005 [0.00, 0.01] win / area 0.77 | 0.006 [0.00, 0.01] win / area 0.78 | 0.005 [0.00, 0.01] win / area 0.77 | 0.005 [0.00, 0.01] win / area 0.77 | 0.006 [0.00, 0.01] win / area 0.77 | 0.006 [0.00, 0.01] win / area 0.77 | 0.005 [0.00, 0.01] win / area 0.77 | 0.005 [0.00, 0.01] win / area 0.77 | 0.005 [0.00, 0.01] win / area 0.77 | 0.005 [0.00, 0.01] win / area 0.77 |

### Stage 4

| contrast | measured_v1 (published) | L1_kc2only | L2_pipe | L3_sel | L3_clk | L3_rc | L3_v2 | L3_lane | L3_laneclk | L3_laneclk_worst | L4_settle20 | L5_ungated | L5_laneratio | L5_mesa0 | L5_mesa1 | L5_worst |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| p3n240: ours_kc2_i11 vs B1_best | 0.490 [0.22, 0.76] inconclusive / area 0.63 | 0.488 [0.22, 0.76] inconclusive / area 0.63 | 0.416 [0.19, 0.65] inconclusive / area 0.63 | 0.417 [0.19, 0.65] inconclusive / area 0.63 | 0.417 [0.19, 0.65] inconclusive / area 0.63 | 0.420 [0.19, 0.65] inconclusive / area 0.63 | 0.495 [0.23, 0.77] inconclusive / area 0.63 | 0.572 [0.26, 0.89] inconclusive / area 0.63 | 0.496 [0.23, 0.77] inconclusive / area 0.63 | 0.496 [0.23, 0.77] inconclusive / area 0.63 | 0.559 [0.26, 0.87] inconclusive / area 0.63 | 0.519 [0.24, 0.80] inconclusive / area 0.63 | 0.489 [0.22, 0.76] inconclusive / area 0.63 | 0.495 [0.23, 0.77] inconclusive / area 0.63 | 0.495 [0.23, 0.77] inconclusive / area 0.63 | 0.495 [0.23, 0.77] inconclusive / area 0.63 |
| p3n240: ours_none vs B1_best | 0.942 [0.91, 0.97] win / area 0.76 | 0.942 [0.91, 0.97] win / area 0.76 | 0.835 [0.80, 0.86] win / area 0.76 | 0.835 [0.80, 0.86] win / area 0.76 | 0.835 [0.80, 0.86] win / area 0.76 | 0.835 [0.80, 0.86] win / area 0.76 | 0.819 [0.80, 0.83] win / area 0.76 | 0.945 [0.92, 0.97] win / area 0.77 | 0.820 [0.80, 0.84] win / area 0.76 | 0.820 [0.80, 0.84] win / area 0.76 | 0.892 [0.87, 0.90] win / area 0.76 | 0.800 [0.79, 0.81] win / area 0.76 | 0.810 [0.79, 0.82] win / area 0.76 | 0.819 [0.80, 0.83] win / area 0.76 | 0.819 [0.80, 0.83] win / area 0.76 | 0.819 [0.80, 0.83] win / area 0.76 |
| p3n480: ours_kc2_i11 vs B1_best | 0.912 [0.26, 1.84] inconclusive / area 0.57 | 0.921 [0.27, 1.86] inconclusive / area 0.57 | 0.756 [0.22, 1.53] inconclusive / area 0.57 | 0.758 [0.22, 1.53] inconclusive / area 0.57 | 0.758 [0.22, 1.53] inconclusive / area 0.57 | 0.760 [0.22, 1.53] inconclusive / area 0.57 | 0.878 [0.26, 1.78] inconclusive / area 0.57 | 1.009 [0.29, 2.04] inconclusive / area 0.57 | 0.891 [0.26, 1.80] inconclusive / area 0.57 | 0.891 [0.26, 1.80] inconclusive / area 0.57 | 0.980 [0.29, 1.98] inconclusive / area 0.57 | 0.931 [0.27, 1.88] inconclusive / area 0.57 | 0.864 [0.25, 1.75] inconclusive / area 0.57 | 0.878 [0.26, 1.78] inconclusive / area 0.57 | 0.878 [0.26, 1.78] inconclusive / area 0.57 | 0.878 [0.26, 1.78] inconclusive / area 0.57 |
| p3n480: ours_none vs B1_best | 0.915 [0.89, 0.93] win / area 0.67 | 0.927 [0.90, 0.94] win / area 0.67 | 0.777 [0.75, 0.79] win / area 0.67 | 0.778 [0.76, 0.79] win / area 0.67 | 0.778 [0.76, 0.79] win / area 0.67 | 0.778 [0.76, 0.79] win / area 0.67 | 0.778 [0.76, 0.79] win / area 0.67 | 0.894 [0.87, 0.91] win / area 0.67 | 0.784 [0.77, 0.79] win / area 0.67 | 0.784 [0.77, 0.79] win / area 0.67 | 0.847 [0.83, 0.85] win / area 0.67 | 0.780 [0.77, 0.78] win / area 0.67 | 0.766 [0.75, 0.77] win / area 0.67 | 0.778 [0.76, 0.79] win / area 0.67 | 0.778 [0.76, 0.79] win / area 0.67 | 0.778 [0.76, 0.79] win / area 0.67 |
| p4n240: ours_kc2_i11 vs B1_best | 0.000 [0.00, 0.00] not evaluable (comparator at 0 % success) / area 0.63 | 0.000 [0.00, 0.00] not evaluable (comparator at 0 % success) / area 0.63 | 0.000 [0.00, 0.00] not evaluable (comparator at 0 % success) / area 0.63 | 0.000 [0.00, 0.00] not evaluable (comparator at 0 % success) / area 0.63 | 0.000 [0.00, 0.00] not evaluable (comparator at 0 % success) / area 0.63 | 0.000 [0.00, 0.00] not evaluable (comparator at 0 % success) / area 0.63 | 0.000 [0.00, 0.00] not evaluable (comparator at 0 % success) / area 0.63 | 0.000 [0.00, 0.00] not evaluable (comparator at 0 % success) / area 0.63 | 0.000 [0.00, 0.00] not evaluable (comparator at 0 % success) / area 0.63 | 0.000 [0.00, 0.00] not evaluable (comparator at 0 % success) / area 0.63 | 0.000 [0.00, 0.00] not evaluable (comparator at 0 % success) / area 0.63 | 0.000 [0.00, 0.00] not evaluable (comparator at 0 % success) / area 0.63 | 0.000 [0.00, 0.00] not evaluable (comparator at 0 % success) / area 0.63 | 0.000 [0.00, 0.00] not evaluable (comparator at 0 % success) / area 0.63 | 0.000 [0.00, 0.00] not evaluable (comparator at 0 % success) / area 0.63 | 0.000 [0.00, 0.00] not evaluable (comparator at 0 % success) / area 0.63 |
| p4n240: ours_none vs B1_best | n/e | n/e | n/e | n/e | n/e | n/e | n/e | n/e | n/e | n/e | n/e | n/e | n/e | n/e | n/e | n/e |
| p4n480: ours_kc2_i11 vs B1_best | 0.320 [0.07, 0.72] inconclusive / area 0.57 | 0.324 [0.07, 0.73] inconclusive / area 0.57 | 0.265 [0.06, 0.60] inconclusive / area 0.57 | 0.265 [0.06, 0.60] inconclusive / area 0.57 | 0.265 [0.06, 0.60] inconclusive / area 0.57 | 0.266 [0.06, 0.60] inconclusive / area 0.57 | 0.316 [0.07, 0.71] inconclusive / area 0.57 | 0.359 [0.08, 0.81] inconclusive / area 0.57 | 0.321 [0.07, 0.73] inconclusive / area 0.57 | 0.321 [0.07, 0.73] inconclusive / area 0.57 | 0.358 [0.08, 0.81] inconclusive / area 0.57 | 0.349 [0.08, 0.79] inconclusive / area 0.57 | 0.311 [0.07, 0.70] inconclusive / area 0.57 | 0.316 [0.07, 0.71] inconclusive / area 0.57 | 0.316 [0.07, 0.71] inconclusive / area 0.57 | 0.316 [0.07, 0.71] inconclusive / area 0.57 |
| p4n480: ours_none vs B1_best | 0.825 [0.81, 0.85] win / area 0.67 | 0.837 [0.82, 0.86] win / area 0.67 | 0.697 [0.68, 0.72] win / area 0.67 | 0.698 [0.69, 0.72] win / area 0.67 | 0.698 [0.69, 0.72] win / area 0.67 | 0.698 [0.69, 0.72] win / area 0.67 | 0.718 [0.70, 0.74] win / area 0.67 | 0.816 [0.80, 0.84] win / area 0.67 | 0.725 [0.71, 0.74] win / area 0.67 | 0.725 [0.71, 0.74] win / area 0.67 | 0.796 [0.79, 0.81] win / area 0.67 | 0.752 [0.74, 0.77] win / area 0.67 | 0.709 [0.70, 0.73] win / area 0.67 | 0.718 [0.70, 0.74] win / area 0.67 | 0.718 [0.70, 0.74] win / area 0.67 | 0.718 [0.70, 0.74] win / area 0.67 |
| dimacs: ours_kc2_i11 vs B1_best | 0.003 [0.00, 0.01] win / area 1.10 | 0.003 [0.00, 0.01] win / area 1.10 | 0.003 [0.00, 0.01] win / area 1.10 | 0.003 [0.00, 0.01] win / area 1.10 | 0.003 [0.00, 0.01] win / area 1.10 | 0.003 [0.00, 0.01] win / area 1.10 | 0.003 [0.00, 0.01] win / area 1.10 | 0.003 [0.00, 0.01] win / area 1.10 | 0.003 [0.00, 0.01] win / area 1.10 | 0.003 [0.00, 0.01] win / area 1.10 | 0.003 [0.00, 0.01] win / area 1.10 | 0.003 [0.00, 0.01] win / area 1.10 | 0.003 [0.00, 0.01] win / area 1.10 | 0.003 [0.00, 0.01] win / area 1.10 | 0.003 [0.00, 0.01] win / area 1.10 | 0.003 [0.00, 0.01] win / area 1.10 |
| dimacs: ours_none vs B1_best | 1.334 [1.13, 1.44] loss / area 1.25 | 1.336 [1.15, 1.44] loss / area 1.25 | 1.147 [0.99, 1.26] inconclusive / area 1.25 | 1.147 [0.99, 1.26] inconclusive / area 1.25 | 1.147 [0.99, 1.26] inconclusive / area 1.25 | 1.147 [0.99, 1.26] inconclusive / area 1.25 | 1.169 [1.00, 1.27] loss / area 1.25 | 1.363 [1.15, 1.49] loss / area 1.26 | 1.162 [1.01, 1.27] loss / area 1.25 | 1.165 [1.01, 1.27] loss / area 1.25 | 1.243 [1.09, 1.35] loss / area 1.25 | 1.230 [1.04, 1.31] loss / area 1.25 | 1.157 [1.00, 1.26] inconclusive / area 1.25 | 1.169 [1.00, 1.27] loss / area 1.25 | 1.169 [1.00, 1.27] loss / area 1.25 | 1.185 [1.00, 1.28] loss / area 1.25 |
| scale verdict (largest N with L1) | None | None | None | None | None | None | None | None | None | None | None | None | None | None | None | None |

Reading. **Max-Cut L2** (ours_none_off vs B1_best, nominal ADC): v1 1.090 loss -> 0.875 once the select tree is pipelined; with the idle clock energy of every machine and the median N = 1024 clock (L3_v2, primary) **0.943**; at the worst N = 1024 clock 0.960. It is **a tie / fragile, not a win**: 1.057 (loss) with the baselines on the lane-path clock and no tree, 1.105 (loss) with free-running lane generators, 0.984 (tie) with a 20 ns analog settle, and the registered verdict flips in 8 of 17 analog corners (section 7). The full-scale-ADC contrast stays below 1 in every column (0.707 primary, 0.835 ungated, 0.792 lane-clock). The Max-Cut Kc2 + I11 arm stays a loss (5.06 primary), **colouring L1** (Stage 3) stays a win (col3p 0.247, col4p 0.005). **Stage 4**: every L1 contrast keeps its registered verdict (inconclusive on p3n240 0.495 / p3n480 0.878 / p4n480 0.316, p4n240 not evaluable) in every column including the worst clock, the scale verdict stays None, so the kill rule result (L1 not replicated at 240) is unchanged; DIMACS Kc2 + I11 stays a win (0.003) with the area loss (1.10), DIMACS ours_none vs B1_best is a loss (1.169). Pricing the restart cycles (L3_rc) changes ratios by 0.001-0.003 (restarts are rare relative to steps); the MESA assumption (0 / 0.5 / 1 of the active spins per reload) moves nothing visible (the headline B1_best arm has no restarts). The idle rule is symmetric (ours, B1, B3 pay the same per-lane, per-cycle energies); what it moves is the sign of the thin Max-Cut L2 margin.

## 6. Activity-annotated power, clock gating and the idle rule (C3, fix 1)

**What the first issue found.** Gate-level runs of the timing study v1 netlists showed that every free-running lane generator costs 0.83-0.89 pJ per clock cycle (3.3-5.3 pJ per step) whether or not it advances: the cost table charged I11 lanes no generator energy and the RTL had no clock gating.

**RTL (this issue).** `rtl/src/clk_gate.v` (clock gate; the negedge-registered enable form equals a latch ICG when the enable changes only after a rising edge, as it does here: it is decoded from FSM state registers), `xoshiro128ss #(GATED)` (no enable multiplexer, the clock only pulses in cycles with `ld` or `adv`), `tim_top` parameter `RNG_CG`
(default 1): one clock gate shared by all N lane generators (enable = seeding shift, or `acc_ld` with `lane_adv`; under I11 the lane generators never see an edge), one for the selection generator (seeding shift, `sel_ld`, restart draw). `RNG_CG = 0` is the v0 structure. The traces of every top-level run are identical with and without gating
(`maxcut16_i7i10_nocg`, `maxcut16_kc2_nocg`, `maxcut16_i11_nocg` in `hw-p3` run `RNG_CG = 0`; all other runs, the spot check and the smoke runs use the gated default and match the golden model bit-exactly). The physical gate is the library cell: `rtl/pnr/tt_wrappers.v` `tt_icg` instantiates Nangate45 `CLKGATETST_X1` (4.5 um2); the gated generator netlist (`xoshiro128ss GATED = 1`) is 1725 um2 post-P&R (1428 um2 synthesised) against 1951 um2 (1562) for the free-running one with its enable multiplexers.

**Measurement.** `scripts/hw_timing/gl_power.py` (as in the first issue: zero-delay gate-level simulation next to the RTL, inputs tapped from RTL signals, every gate-level output compared with the RTL at every negedge, OpenSTA `read_vcd` + `report_power`), now with the gated generator netlist and both library clock gates in the simulation (the gate-level gate output is compared with the RTL `gclk` one picosecond after every rising edge).
Two measurement points that matter: (a) OpenSTA derives the activity of a clock network from the SDC clock, so a gated clock needs the real pulse rate: `sta_power` reads the VCD clock period from STA's own warning and re-runs with it as the SDC period (and a clock that never pulses in the window, like the lane generators under I11, is reported as zero dynamic energy); (b) the quiet (idle) energy per cycle of every block is measured with `scripts/hw_timing/gl_idle.py` (clock toggling, data inputs constant, 80 cycles).
All 12 gate-level runs have 0 mismatches against the RTL.

| run | N | cycles/step | lane logic fJ/step (table rows) | lane generator fJ/step per generator (table row) | select tree fJ/step | two clock gates fJ/step |
|---|---|---|---|---|---|---|
| col64_kc2_i11__cg | 64 | 5 | 1112 (456) | 0 (18) | 3415 | 66 |
| col64_kc2_i11__pipe | 64 | 5 | 1118 (456) | 4436 (18) | 3414 | 0 |
| col64_kc2_i11__v1 | 64 | 4 | 905 (456) | 3549 (18) | 324 | 0 |
| maxcut256_kc2_i11__cg | 256 | 6 | 1378 (1119) | 0 (4) | 15936 | 80 |
| maxcut256_kc2_i11__pipe | 256 | 6 | 1378 (1119) | 5324 (4) | 15936 | 0 |
| maxcut256_kc2_i11__v1 | 256 | 4 | 992 (1119) | 3550 (4) | 3764 | 0 |
| maxcut64_kc2_i11__cg | 64 | 5 | 1078 (1122) | 0 (17) | 3370 | 64 |
| maxcut64_kc2_i11__pipe | 64 | 5 | 1082 (1122) | 4436 (17) | 3384 | 0 |
| maxcut64_kc2_i11__v1 | 64 | 4 | 881 (1122) | 3549 (17) | 739 | 0 |
| maxcut64_none__cg | 64 | 5 | 2051 (1233) | 1332 (916) | 3415 | 69 |
| maxcut64_none__pipe | 64 | 5 | 2051 (1233) | 3957 (916) | 3415 | 0 |
| maxcut64_none__v1 | 64 | 4 | 1745 (1233) | 3321 (916) | 850 | 0 |

`__v1`: single-cycle tree, free-running generators; `__pipe`: pipelined tree, free-running generators; `__cg`: pipelined tree, gated generators and library clock gates (the final RTL, `RNG_CG = 1`). Lane figures are per lane, generator figures per generator, the tree is the whole tree.

Reading: the gated generators cost 1332 fJ per advance (ungated 3321 fJ per step at 4 cycles per step), nothing under I11, and the two clock gates 64-80 fJ per step in total. The select tree and controller numbers are mostly clock energy of registers that are clocked every cycle, which is why the idle energy rule below is stated per cycle.

**Idle energy per cycle (quiet netlists).** The energy one clock cycle costs when nothing happens, per block, in pJ per cycle (sum over the machine):

| N | lane logic x N | select tree (A) | controller (A) | Kc2-only restart unit | full restart unit | lane generators ungated (x N) | generator clock gates (2) |
|---|---|---|---|---|---|---|---|
| 64 | 14.7 | 0.70 | 1.93 | 5.15 | 5.29 | 57.0 | 0.011 |
| 128 | 29.4 | 1.38 | 2.40 | 9.00 | 9.23 | 114.0 | 0.011 |
| 256 | 58.8 | 2.82 | 3.31 | 17.30 | 17.70 | 227.9 | 0.011 |
| 512 | 117.5 | 5.50 | 5.11 | 35.39 | 36.13 | 455.8 | 0.011 |
| 1024 | 235.0 | 10.86 | 8.69 | 74.85 | 76.27 | 911.7 | 0.011 |

**The idle rule (all machines, one rule).** `MeasuredCostV2(idle_charge=True)` charges every cycle of every machine: its lanes x the lane-logic idle energy (lanes = padded N for ours, n_act for B1 and B3), the two generator clock gates (generators gated: nothing else), the select tree and the controller for machines that carry the tree (same-tree assumption for B1 / B3, as for the clock), and the restart unit for machines that have one (ours Kc2: Kc2-only unit, B1 MESA: full unit). It sits on top of the per-operation rows of the table (an operation's own clock part is then counted twice, so the rule is conservative by at most that part). The ungated variant (`gen_gated=False`, `L5_ungated`) charges every lane generator its free-running clock instead of the gates.
The lane logic, the select tree, the controller and the restart unit are not clock-gated in the RTL (gating them is a design option, not taken): their idle energy is charged as measured, equally to every machine that has them.

## 7. Parameterised analog model and sensitivity (C5)

`scripts/hw_timing/analog_model.py` (replaces the area-only `area_model.py` for analog parts; `area_model.py` is kept) makes every analog number an explicit parameter with a low / nominal / high value
taken from the cost-table bands; none is measured here (no FeFET PDK, no ADC layout):

| parameter | low | nominal | high | source |
|---|---|---|---|---|
| a_array_cell (um2 per cell) | 0.015 | 0.15 | 0.30 | Zhou NC 2025 2FeFET cell (upper value for 1FeFET1R), band from the table (0.1x - 2x) |
| a_adc_col (um2 per column ADC) | 129 | 430 | 1290 | built-up 8 b SAR estimate, band 0.3x - 3x |
| e_array_cell_read (fJ) | 0.126 | 0.252 | 0.503 | char_v1 SPICE, band 0.5x - 2x |
| e_adc_conv_bit (fJ) | 22.8 | 45.6 | 91.2 | char_v1 SPICE comparator + analytic C-DAC, band 0.5x - 2x |
| e_adc_bias_step (fJ) | 39 | 195 | 975 | ADC comparator bias held per ungated step, band 0.2x - 5x |
| t_array_settle (ns) | 10 | 20 | 40 | char_v1 read window (`t_cim_verify_read` = 0.02 us), band 0.5x - 2x |

Functions: `parameters()`, `tile_area(arch, corner)`, `step_energy(counters, steps, corner)`, `settle_cycles(t_ns, t_clk)`, `sensitivity_corners()`. Example (w_bits = 2, Kc2 + I11) tile analog area at N = 256 / 512 / 1024:
0.14 / 0.48 / 1.40 mm2, 0.28 / 1.04 / 2.96 mm2, 0.59 / 2.39 / 6.54 mm2 (low / nominal / high).

**Array settle in ns (new, a direct consequence of the faster clock).** The golden counters charge one array-settle cycle per CiM read (`cim_array_lat = 1`); at 9.15 ns that is about 9 ns, at 2.4 ns it is
only 2.4 ns although the analog settle does not scale with the digital clock. The v2 model therefore prices the settle in ns when asked (`settle_ns`; `ceil(t / t_clk)` cycles per read); the registered
cycle-rule primary (L3_v2) keeps the one-cycle rule so it stays comparable with v1, and L4_settle20 (20 ns) is the stated physical sensitivity.

**Corner re-pricing.** One-at-a-time low / high of each parameter and the all-low / all-high corners, on the primary pricing (L3_v2), both stages
(`reprice_all.sh <stage> analog`; outputs `docs/hw/results/timing_v2/h{6,7}_analog_<corner>.{json,md}`). Cells: ETS99 ratio, energy verdict; A = area ratio and verdict. Area parameters
(`a_*`) move only the area ratio, energy parameters only the energy ratio. Corners are on the final primary pricing (L3_v2, idle rule included), so the energy ratios include the measured idle energy. "-" = not run for that stage.

| corner | maxcut: ours_none_off | maxcut: ours_none_fs | col3p: ours_kc2_i11_off | p3n240: ours_kc2_i11 | p3n480: ours_kc2_i11 | p4n480: ours_kc2_i11 | dimacs: ours_kc2_i11 | dimacs: ours_none |
|---|---|---|---|---|---|---|---|---|
| nominal | 0.943 win; A 0.74 win | 0.707 win; A 0.74 win | 0.247 win; A 0.77 win | 0.495 inconclusive; A 0.63 win | 0.878 inconclusive; A 0.57 win | 0.316 inconclusive; A 0.57 win | 0.003 win; A 1.10 loss | 1.169 loss; A 1.25 loss |
| e_array_cell_read_lo | 0.930 win; A 0.74 win | 0.692 win; A 0.74 win | 0.246 win; A 0.77 win | 0.491 inconclusive; A 0.63 win | 0.863 inconclusive; A 0.57 win | 0.310 inconclusive; A 0.57 win | 0.003 win; A 1.10 loss | 1.144 inconclusive; A 1.25 loss |
| e_array_cell_read_hi | 0.969 tie; A 0.74 win | 0.735 win; A 0.74 win | 0.248 win; A 0.77 win | 0.504 inconclusive; A 0.63 win | 0.907 inconclusive; A 0.57 win | 0.326 inconclusive; A 0.57 win | 0.003 win; A 1.10 loss | 1.219 loss; A 1.25 loss |
| e_adc_conv_bit_lo | 1.073 loss; A 0.74 win | 0.830 win; A 0.74 win | 0.258 win; A 0.77 win | 0.524 inconclusive; A 0.63 win | 0.940 inconclusive; A 0.57 win | 0.346 inconclusive; A 0.57 win | 0.003 win; A 1.10 loss | 1.267 loss; A 1.25 loss |
| e_adc_conv_bit_hi | 0.814 win; A 0.74 win | 0.585 win; A 0.74 win | 0.229 win; A 0.77 win | 0.451 inconclusive; A 0.63 win | 0.792 inconclusive; A 0.57 win | 0.276 inconclusive; A 0.57 win | 0.003 win; A 1.10 loss | 1.051 inconclusive; A 1.25 loss |
| e_adc_bias_step_lo | 0.943 win; A 0.74 win | 0.707 win; A 0.74 win | 0.247 win; A 0.77 win | 0.495 inconclusive; A 0.63 win | 0.878 inconclusive; A 0.57 win | 0.316 inconclusive; A 0.57 win | 0.003 win; A 1.10 loss | 1.169 loss; A 1.25 loss |
| e_adc_bias_step_hi | 0.943 win; A 0.74 win | 0.707 win; A 0.74 win | 0.247 win; A 0.77 win | 0.495 inconclusive; A 0.63 win | 0.878 inconclusive; A 0.57 win | 0.316 inconclusive; A 0.57 win | 0.003 win; A 1.10 loss | 1.169 loss; A 1.25 loss |
| a_array_cell_lo | 0.943 win; A 0.72 win | 0.707 win; A 0.72 win | 0.247 win; A 0.77 win | 0.495 inconclusive; A 0.62 win | 0.878 inconclusive; A 0.56 win | 0.316 inconclusive; A 0.56 win | 0.003 win; A 1.07 loss | 1.169 loss; A 1.22 loss |
| a_array_cell_hi | 0.943 win; A 0.76 win | 0.707 win; A 0.76 win | 0.247 win; A 0.78 win | 0.495 inconclusive; A 0.63 win | 0.878 inconclusive; A 0.58 win | 0.316 inconclusive; A 0.58 win | 0.003 win; A 1.13 loss | 1.169 loss; A 1.28 loss |
| a_adc_col_lo | 0.943 win; A 1.01 tie | 0.707 win; A 1.01 tie | 0.247 win; A 0.83 win | 0.495 inconclusive; A 0.76 win | 0.878 inconclusive; A 0.73 win | 0.316 inconclusive; A 0.73 win | 0.003 win; A 1.29 loss | 1.169 loss; A 1.55 loss |
| a_adc_col_hi | 0.943 win; A 0.56 win | 0.707 win; A 0.56 win | 0.247 win; A 0.69 win | 0.495 inconclusive; A 0.47 win | 0.878 inconclusive; A 0.42 win | 0.316 inconclusive; A 0.42 win | 0.003 win; A 0.93 win | 1.169 loss; A 1.01 tie |
| t_array_settle_lo | 0.965 tie; A 0.74 win | 0.744 win; A 0.74 win | 0.256 win; A 0.77 win | 0.533 inconclusive; A 0.63 win | 0.928 inconclusive; A 0.57 win | 0.337 inconclusive; A 0.57 win | 0.003 win; A 1.10 loss | 1.209 loss; A 1.25 loss |
| all_lo | 1.075 loss; A 0.98 tie | 0.851 win; A 0.98 tie | 0.265 win; A 0.82 win | 0.555 inconclusive; A 0.76 win | 0.975 inconclusive; A 0.71 win | 0.361 inconclusive; A 0.71 win | 0.003 win; A 1.24 loss | 1.276 loss; A 1.51 loss |
| t_array_settle_hi | 1.015 tie; A 0.74 win | 0.831 win; A 0.74 win | 0.271 win; A 0.77 win | 0.593 inconclusive; A 0.63 win | 1.049 inconclusive; A 0.57 win | 0.388 inconclusive; A 0.57 win | 0.003 win; A 1.10 loss | 1.294 loss; A 1.25 loss |
| all_hi | 0.901 win; A 0.56 win | 0.710 win; A 0.56 win | 0.259 win; A 0.69 win | 0.562 inconclusive; A 0.47 win | 0.985 inconclusive; A 0.43 win | 0.355 inconclusive; A 0.43 win | 0.003 win; A 0.95 tie | 1.208 loss; A 1.02 tie |
| L5_ungated | 1.105 loss; A 0.74 win | 0.835 win; A 0.74 win | 0.277 win; A 0.77 win | 0.519 inconclusive; A 0.63 win | 0.931 inconclusive; A 0.57 win | 0.349 inconclusive; A 0.57 win | 0.003 win; A 1.10 loss | 1.230 loss; A 1.25 loss |
| L5_laneratio | 0.932 win; A 0.74 win | 0.702 win; A 0.74 win | 0.246 win; A 0.77 win | 0.489 inconclusive; A 0.63 win | 0.864 inconclusive; A 0.57 win | 0.311 inconclusive; A 0.57 win | 0.003 win; A 1.10 loss | 1.157 inconclusive; A 1.25 loss |
| L5_mesa0 | 0.943 win; A 0.74 win | 0.707 win; A 0.74 win | 0.247 win; A 0.77 win | 0.495 inconclusive; A 0.63 win | 0.878 inconclusive; A 0.57 win | 0.316 inconclusive; A 0.57 win | 0.003 win; A 1.10 loss | 1.169 loss; A 1.25 loss |
| L5_mesa1 | 0.943 win; A 0.74 win | 0.707 win; A 0.74 win | 0.247 win; A 0.77 win | 0.495 inconclusive; A 0.63 win | 0.878 inconclusive; A 0.57 win | 0.316 inconclusive; A 0.57 win | 0.003 win; A 1.10 loss | 1.169 loss; A 1.25 loss |
| L5_worst | 0.960 tie; A 0.74 win | 0.720 win; A 0.74 win | 0.247 win; A 0.77 win | 0.495 inconclusive; A 0.63 win | 0.878 inconclusive; A 0.57 win | 0.316 inconclusive; A 0.57 win | 0.003 win; A 1.10 loss | 1.185 loss; A 1.25 loss |

verdict changes against nominal: e_array_cell_read_lo: dimacs ours_none vs B1_best energy: loss -> inconclusive; e_array_cell_read_hi: maxcut ours_none_off vs B1_best energy: win -> tie; e_adc_conv_bit_lo: maxcut ours_none_off vs B1_best energy: win -> loss; e_adc_conv_bit_hi: dimacs ours_none vs B1_best energy: loss -> inconclusive; a_adc_col_lo: maxcut ours_none_off vs B1_best area: win -> tie; a_adc_col_lo: maxcut ours_none_fs vs B1_best area: win -> tie; a_adc_col_hi: dimacs ours_kc2_i11 vs B1_best area: loss -> win; a_adc_col_hi: dimacs ours_none vs B1_best area: loss -> tie; t_array_settle_lo: maxcut ours_none_off vs B1_best energy: win -> tie; all_lo: maxcut ours_none_off vs B1_best energy: win -> loss; all_lo: maxcut ours_none_off vs B1_best area: win -> tie; all_lo: maxcut ours_none_fs vs B1_best area: win -> tie; t_array_settle_hi: maxcut ours_none_off vs B1_best energy: win -> tie; all_hi: dimacs ours_kc2_i11 vs B1_best area: loss -> tie; all_hi: dimacs ours_none vs B1_best area: loss -> tie; L5_ungated: maxcut ours_none_off vs B1_best energy: win -> loss; L5_laneratio: dimacs ours_none vs B1_best energy: loss -> inconclusive; L5_worst: maxcut ours_none_off vs B1_best energy: win -> tie


## 8. Lint and SPEC (C6)

* `rtl/verilator/lint.sh`: Verilator `--lint-only` default and `-Wall`, N = 8 / 64 / 256, CIM = 1, TCL = 1, for four builds (v0, pipelined tree with all cuts and the Kc2-only restart unit, pipelined tree with no extra
  cuts, ungated generators `RNG_CG = 0`). Output: `LINT OK`. `select_tree_pipe` needed four explicit width fixes (conditional tests on 32-bit parameters); no waiver was added.
* `docs/rtl/SPEC_v0.md`: config offsets 22-31 added (they existed in `hw/p3-rtl` but not in this tree's SPEC), offset 32 (`adc_fs`, I7v2) documented, new parameters `SEL_PIPE`, `SEL_ADD_CUT`, `SEL_WALK_CUT`,
  `RS_MESA`, derived `SEL_LAT`, state SEL with `SEL_LAT` cycles, per-step cycle formulas, module rows for `select_tree_pipe`, `lam_ramp`, `hold_ctl`, `lane_rnd_mux`.
* `tb_top` forwards `CIMWB`; `rtl/verilator/smoke.sh` skips (reports) runs that this tree's generator does not produce instead of failing on them.
* Test results (final RTL): `hw-p5b` `scripts/run_rtl_tests.sh --long` 54/54, `hw-p3` `scripts/run_rtl_tests.sh --long` 60/60, `tests/hw` pytest: see the internal review.


## Internal review (second issue)


* `hw-p5b`, branch `hw/p4-baselines`: first issue `8669bb2`, `839d75f`, `8b5f9e6`, `b532349`; second issue `e34f8f2` (RTL: `clk_gate`, gated `xoshiro128ss`, `RNG_CG`, pipelined `restart_unit`; `MeasuredCostV2` idle rule and symmetric restart clock; gate-level idle / gated-power scripts; restart tests at N = 64 / 256),
  `76d302f` (measured_v2 tables on the final RTL, Stage 3 / 4 ladder, analog corners, gated gate-level power, this document) and the commit after it (final numbers of this internal review section).
* `hw-p3`, branch `hw/p3-rtl`: first issue `fc58a7a`; second issue `5e5117a` (RTL identical to `hw-p5b`, golden `sel_lat` / `gen_tests` changes) and `f58ee82` (SPEC_v0 sync).


`cost_model.py` and `pricing.py` got additions only
(`MeasuredCostV2`, `measured_v2_table`, `CostModel.adjust_counters` hook + one call in `pricing.price`); the default `CostModel()` hash is unchanged (`test_default_cost_model_unchanged_by_v2`, `test_default_table_is_unchanged_canonical`).

### Claims and evidence (fix-list item / checklist item -> claim -> evidence)

| id | claim | evidence (test / command / output path) |
|---|---|---|
| F1.1 | Idle lane generators are clock-gated in the RTL (one gate for all lane generators, one for the selection generator) and nothing changes functionally | `rtl/src/clk_gate.v`, `xoshiro128ss.v`, `tim_top.v` (`RNG_CG`); `scripts/run_rtl_tests.sh --long` 54/54 (`sim/out/t2e_rtl_tests_long.log`; gated default everywhere, `RNG_CG = 0` in `maxcut16_i7i10_nocg`, `maxcut16_kc2_nocg`); `rtl_spotcheck.py --sel off|mid|max` 44/44 each (`sim/out/t2e_spot_*.log`); `hw-p3` 60/60 incl. `maxcut16_i11` / `_i5` with gated clocks and `maxcut16_i11_nocg` |
| F1.2 | The library clock gate and the gated generator netlist behave like the RTL | `scripts/hw_timing/gl_run_all.sh ... cg`: 4 gate-level runs with `gl_icg` + gated `gl_rng` netlists, 0 mismatches (`sim/out/hw/t2_gl/*__cg/gl_power.json`, `mismatches`) |
| F1.3 | Gated energies re-measured with the real pulse rate | `scripts/hw_timing/gl_power.py` (`sta_power`: VCD clock period -> SDC period; zero toggles -> zero dynamic energy; `vcd_toggles`); `docs/hw/results/timing_v2/gl_power_summary.json`; STA logs `sim/out/hw/t2_gl/*__cg/sta_*.log` |
| F1.4 | Idle energy of every block measured, charged to every machine under one rule | `scripts/hw_timing/gl_idle.py`, `gl_idle_all.py`, `sim/out/hw/t2b_idle/*/idle.json`; rows `tt_e_idle_*` in `docs/hw/energy_table_measured_v2_blocks.csv`; `MeasuredCostV2.charge_restart_unit`; tests `test_idle_energy_is_charged_to_every_machine_under_one_rule`, `test_ungated_generators_cost_every_lane_every_cycle`, `test_idle_charge_can_be_switched_off_and_restart_unit_idle_is_charged` |
| F1.5 | Stage 3 / 4 re-priced offline under the idle rule | `h{6,7}_L3_v2.{json,md}` (primary), `h{6,7}_L5_ungated.*` (ungated generators), ladder in section 5 |
| F2.1 | The restart path is pipelined; golden / RTL bit-exact | `rtl/src/restart_unit.v` (R_DRAW / R_ADD / R_SWP1 / R_SWAP / R_RD kick, R_ENC / R_CHK encoder, 2-stage permutation init); `tb_restart` 88,805 checks; RTL runs `qubo64_kc2`, `qubo64_mesa`, `qubo256_kc2`, `qubo256_mesa` (restarts at N >= 64: 28 / 86 / 1 / 1 restarts) and `maxcut16_*` PASS; spot check 44/44 |
| F2.2 | Restart units measured at 5 sizes, both builds | `restart_N*`, `restartk_N*` in `sim/out/hw/timing_v1/t2b/` (N = 1024: `t2u30/`), rows `tt_{t,a,p_leak,e_idle}_{restart,restartk}_n*`; first-issue (unpipelined) values kept as `restart0` / `restartk0`; table in section 2 |
| F3.1 | B1 and ours get the same restart-clock rule | `MeasuredCostV2.at` / `restart_stem`; `test_restart_unit_is_in_the_clock_of_every_machine_that_has_one`; ladder step L3_clk |
| F4.1 | Re-runs on the final RTL | p5b: `run_rtl_tests.sh --long` 54/54, `rtl_spotcheck.py` 44/44 x3, `lint.sh` OK, `smoke.sh` 0 failed (5 skipped: runs this tree's generator does not produce); `hw-p3`: `run_rtl_tests.sh --long` 60/60, `smoke.sh` 0 failed, `lint.sh` OK, spot check against `hw-p3` RTL (`HW_RTL_ROOT`) 44/44 x3 (`sim/out/t2e_p3_spot_*.log`, `hw-p3/sim/out/t2e_p3_*.log`) |
| F4.2 | `hw-p3` carries the golden `sel_lat` changes and identical RTL | `hw-p3` commit 5e5117a: `scripts/golden/counters.py`, `gen_tests.py` (`_sl`, `nomesa`, `nocg`, restart-at-N runs), `rtl/` byte-identical to `hw-p5b` (`diff -r hw-p5b/rtl hw-p3/rtl` empty apart from `pnr/` and `cfg/`) |
| C1-C6 | the first-issue claims (C1 select tree, C2 Kc2-only unit, C4 measured N, C5 analog model, C6 lint / SPEC) stand | sections 1, 2, 3, 7, 8; the tables of sections 5-7 were regenerated on the final RTL |
| F5.1 | Restart cycles priced, cycle-exact against the RTL | golden `restart_cycles` vs RTL `rs_cycles`: `sim/out/t2j_rtl_tests_long.log` (54/54, "S_RST cycles equal the golden model"), `t2j_spot_*.log` 44/44 x 3, `hw-p3` 60/60 + 44/44 x 3 (`hw-p3/sim/out/t2j_p3_*`); `MeasuredCostV2.adjust_counters`; `h{6,7}_L3_rc.*`, `L5_mesa0/1`; tests `test_golden_restart_cycles_follow_the_rtl_fsm_formulas`, `test_restart_cycles_are_priced_per_restart_and_old_raw_records_use_the_stated_rule` |
| F5.2 | N = 1024 P&R variance bounded, one rule, Max-Cut L2 priced at median and worst clock | `rtl/pnr/run_timing_v2.sh --pnr-one`, `scripts/hw_timing/t2_seed_runs.sh`, `sim/out/hw/timing_v1/t2seed/`, `docs/hw/results/timing_v2/pnr_variance_1024.json`, `t2_report.py` (variance rows `*_n1024`, `*_worst`); `h6_L3_v2.*`, `h6_L5_worst.*`; test `test_worst_clock_statistic_uses_the_worst_rows_when_present` |
| F7.1 | Every priced table draws its restart / tree / idle rows from the same block table | all `h{6,7}_*.json` (60) re-priced after the last table change (ladder, annotated, 15 x 2 analog corners) carry `blocks_sha256` of `docs/hw/energy_table_measured_v2_blocks.csv`; test `test_every_priced_table_draws_its_block_rows_from_the_same_source`; no registered verdict or label and no ETS ratio (to 4 digits) changed against the previous commit (62 files compared) |
| F6.1 | Restart-unit seed study complete (3 seeds each, 30 %) and priced; the sensitivity row L3_laneclk is re-priced at the restart medians and worst (not dropped) | `sim/out/hw/timing_v1/t2seed/restart*_N1024_s*_u30`, `pnr_variance_1024.json`, `h{6,7}_L3_laneclk.*`, `h{6,7}_L3_laneclk_worst.*`; section 4b |
| F5.3 | Max-Cut L2 labelled tie / fragile everywhere | summary, "Third issue", section 5 |
| R.1 | Re-pricing is valid because selection behaviour is unchanged | section 5; `MeasuredCostV2.adjust_counters` adds only `steps * (SEL_LAT - 1)`; `test_pipelined_repricing_adds_exactly_the_latency_cycles` |

Tests: `tests/hw/test_timing_v2.py` (24 collected, the Verilator ones skip without Verilator), `rtl/tb/tb_select_pipe.v`, the T2 top-level runs, `--sel` modes of `rtl_spotcheck.py`. Full `tests/hw` suite on the final tree: 536 passed in 113 s (`python -I -m pytest tests/hw -q -x`, swref env, run directly).

### Known gaps (not hidden)

1. **Restart cycles are priced** (Kc2 6L + 1, MESA 4d + 3 per restart; cycle-exact against the RTL). For the stored Stage 3 / 4 raw records the cycles are derived from the restart count: Kc2 kick size L = 10 unless the record says otherwise (the Stage 3 L = 40 sweep arms are therefore priced as L = 10: under-counted, not in any headline), MESA differing spins = 0.5 n_act (the raw records do not keep the Hamming distance; 0 and 1 bound it, `L5_mesa0` / `L5_mesa1`). New counters carry the exact `restart_cycles`.
2. **P&R variance.** Bounded at N = 1024 (section 4b): trees 3 seeds x 2 utilisations + main run, both restart units 3 seeds at 30 % + main run (the 60 %-utilisation restart-unit runs are congestion-dominated global-route estimates, 6.59 / 3.19 ns against post-placement slack >= 0, excluded by the stated rule and listed). N <= 512 are single runs; the lane (2.41 ns) and RNG (2.32 ns) paths and the N = 1024 controller are single runs too. The N = 1024 spread (+-8 % around the median for the tree, 1.77-2.89 ns for the Kc2-only unit) is the stated bound on single-run numbers. Only the variants listed in `reprice_all.sh recheck3` (L3_v2, L3_laneclk, L3_laneclk_worst, L5_worst, L3_lane, L5_ungated) were re-priced after the restart rows moved to their medians; the other ladder columns and the analog corners were priced with the main-run restart rows (path 2.18 / 2.80 ns): they differ only in restart area / leakage (below 1 %) and do not bind a clock.
3. **Heuristic cut-mask search** (152 completed configurations; rule A / B), one seed, 2.4 ns synthesis target, 240-420 s P&R timeout; the rule-B N = 1024 point is 2.454 ns, 2 % above the lane path.
4. **Same timing study v1 limits**: Nangate45 typical corner, global route, post-route data arrival with ports standing for flops, 60 % utilisation (30 % for the N = 1024 restart units).
5. **Gate-level power limits**: 4 sampled lanes, 400 / 150 steps, N = 64 / 256 runs (the 256-lane run with the CiM off for speed), zero-delay simulation, ideal clock (the clock tree itself, i.e. the wire and buffer energy of distributing the gated clock to N x 128 generator flops, is not modelled: the gate-level runs include flop clock-pin and sequential energy, not clock-tree wires); the idle rows are N = 64 .. 1024 netlist measurements of quiet blocks; lane logic, select tree, controller and restart unit are not clock-gated (charged as measured).
6. **Analog numbers remain cited / SPICE stand-ins.** The 20 ns array settle is the char_v1 read window; L4 and the corners are sensitivities, the registered primary keeps the one-cycle settle (as in v1).
7. **B1 / B3 internals** (select logic, lane gating) were never synthesised: same-tree and same-lane assumptions, one rule for all machines; the BASELINES_V2 own-clock rows (B3 lane 2.687 ns, B1 lane 2.409 ns) are not combined with measured_v2.
8. `RS_MESA = 0` leaves arm 2 (mesa) inert (build option for Kc2 / none / da_offset only). `hw-p5b`'s `gen_tests.py` does not generate the tweak runs (`maxcut16_i11`, `_i5`, `knap16_i3`, `knap16_tcamlite`); they run in `hw-p3`, the smoke script reports them as skipped here.
9. The Stage 3 / 4 raw records are `sim/out/hw/stage{3,4}` (gitignored, unpacked from the cloud return package); the committed `h6_*` / `h7_*` outputs are the re-pricings.

## Internal review verdict (17 Nov 2026)

Re-run by the checker: `tests/hw/test_timing_v2.py` 17 passed (swref env); `rtl_spotcheck.py --sel mid` 44/44 bit-exact (via local job queue); `rtl/verilator/lint.sh` LINT OK (N = 8/64/256, default and -Wall). Diffs of `restart_unit.v`, `tim_top.v` (`RS_MESA`), `cost_model.py` (`MeasuredCostV2`) read.

| item | verdict | evidence / reason |
|---|---|---|
| C1 pipelined select tree | PASS | tb_select_pipe, golden `sel_lat` cycle-exact, spotcheck re-run 44/44; `adjust_counters` adds only `steps*(SEL_LAT-1)`, so no golden/RTL selection divergence. 9.15 -> 3.06 / 2.45 ns (heuristic grid, single seed; disclosed). |
| C2 Kc2-only unit | PASS | `MESA=0` gates `is_mesa` and removes the `diff = x ^ best_x` encoder path (restart_unit.v:65,79); area is explained: 10,240 of 10,395 flops are the Fisher-Yates `perm` table (restart_unit.v:63), which Kc2 needs. +2.4 % at N=1024 is within P&R noise. Measured and charged. |
| C3 activity-annotated power | FAIL (consistency) | Gate-level runs are real (8 runs, 0 mismatches), but the primary measured_v2 still assumes idle lane generators draw nothing while the RTL has no clock gating; the ungated energy is charged only in L5_annot, only for our own I11 machines (cost_model.py:372-376), and it doubles the p3n240 ratio (0.48 -> 0.95). |
| C4 measured N | PASS | `*_n128`, `*_n512` rows measured; `_at` exact-key lookup. |
| C5 analog model | PASS | `analog_model.py` with ranges, 15 corners x 2 stages, tests bracket nominal; settle stays a cited stand-in (disclosed). |
| C6 lint / SPEC | PASS | LINT OK re-run; SPEC rows 22-32, SEL_LAT documented. |

**Not yet accepted.** Fix list:

1. `rtl/src/tim_top.v:272` (rng generate block): implement clock-enable/ICG gating of idle lane generators (enable = lane active in the current step mode), re-run the 8 gate-level annotated runs, and make the measured gated energy the primary. If gating is not implemented, then `scripts/golden/cost_model.py:372-376` must charge `gen_idle_cycle_fj` in the primary measured_v2 for every machine that carries idle generators, baselines included (remove the `_own_tree` and `tweak == "i11"` restriction for this term), and re-issue the Stage 3/4 tables and verdicts.
2. `rtl/src/restart_unit.v:130` (R_DRAW): pipeline the Kc2 restart path (register the perm-table read before the swap / add a draw state, update golden restart cycle count and `gen_tests` restart cases), so the Kc2 clock is set by the select tree/lane, not 3.83 ns; re-measure `restartk_N*`. Alternatively declare and justify a multicycle path with STA proof.
3. `scripts/golden/cost_model.py:351` (`restart_in_clock`): apply the same rule to B1's MESA unit (14.08 ns) as to ours, or report B1 both ways in the primary table; the current asymmetric treatment favours B1 and must at least be a stated primary-table column.
4. After 1-3, re-run `run_rtl_tests.sh --long`, `rtl_spotcheck --sel off/mid/max`, lint, smoke, and port the golden `sel_lat`/spotcheck changes to `hw-p3` (gap 8) so both RTL branches verify identically.

## Internal re-check 2 (17 Nov 2026, after 6005bba)

Re-run: `tests/hw/test_timing_v2.py` 21 passed; `lint.sh` LINT OK. Read: `tim_top.v:271-277` (`RNG_CG`, `clk_gate` on lane and selection generators), `cost_model.py:307` (one idle rule: gated primary, `RNG_CG = 0` sensitivity for every machine), restart-unit split into registered steps.

| previous fix | status |
|---|---|
| 1 idle generators | DONE: gated in RTL, re-measured at gate level, same rule for ours / B1 / B3 |
| 2 restart path | DONE: pipelined (1.6-2.8 ns). N = 1024 closes only at 30 % utilisation, so its area is not comparable to 60 % rows without a note |
| 3 symmetric MESA clock | DONE |
| 4 re-runs / hw-p3 port | DONE per internal review (54/54, 60/60, spotcheck 44/44 x3) |

C1, C2, C4, C5, C6: PASS. C3: PASS. **Not accepted** yet, for two pricing and robustness gaps:

1. **Restart cycles are not priced** (section at line ~321: about 6L + 2 = 62 cycles per Kc2 restart, 4 cycles per differing spin per MESA reload). Add them to the golden counters (`scripts/golden/counters.py`, restart path) checked cycle-exact against the RTL `S_RST` count, add them in `MeasuredCostV2.adjust_counters` (`scripts/golden/cost_model.py`), and re-issue the Stage 3/4 tables. This affects both the Kc2 arm and the MESA arm (B1).
2. **P&R variance at N = 1024 is unbounded**, and the Max-Cut L2 win (0.939) flips under each sensitivity (lane clock 1.045, 20 ns settle 0.979, ungated 1.102). Run at least 3 placement seeds x 2 utilisations (30 / 45 %, plus 60 % where it closes) for the select tree, the restart unit and the lane at N = 1024. Report the min / median / max clock, and price L2 at the worst and median values. Area at different utilisations must use one stated rule.
3. After 1-2, state in the Stage 3 text that the Max-Cut result is a tie or fragile, not a win, unless it stays below 1 across the seed range and the restart-cycle pricing.

## Internal re-check 3 (17 Nov 2026, after 8e5e58e)

Re-run: `tests/hw/test_timing_v2.py` 24 passed. Read: `cost_model.py:308-310` (restart cycles: Kc2 6 per kick + 1, MESA 4 per differing spin + 3, checked cycle-exact against the RTL), section 4b (seed study), line 172.

| previous fix | status |
|---|---|
| 1 restart cycles priced | DONE (counters and MeasuredCostV2; MESA Hamming distance bracketed by L5_mesa0/1, ratios move 0.001-0.003) |
| 2 N = 1024 P&R variance | DONE for the select tree (3 seeds x 2 utilisations, median 3.147 ns primary, worst 3.526 ns as a sensitivity). PARTIAL for the restart units |
| 3 Max-Cut wording | DONE (tie / fragile everywhere) |

C1-C6: PASS on the primary columns. **Not accepted**: one item remains.

1. The restart-unit seed study *does* bind a priced column. `L3_laneclk` (`scripts/hw_timing/reprice_v2.py:44`, `tree="lane"`, with `restart_in_clock` on by default) uses the rule-B tree at about 2.47 ns. The priced restart units are 2.18 / 2.80 ns, and the Kc2-only seed runs reach up to 2.89 ns. So the restart unit sets the clock in that row, priced from one run (the full unit has one seed). Fix: run at least 3 seeds for the full (MESA) restart unit at 30 %. Re-price `L3_laneclk` (and any other rule-B row) with the median restart-unit clock, add a worst-case variant, and state in section 4b that the restart unit binds under rule B. Alternatively, drop rule B from the priced rows.

## Internal re-check 4 (17 Nov 2026, after 4ca1105)

Re-run: `tests/hw/test_timing_v2.py` 24 passed. The re-check 3 fix is done. The full restart unit now has 3 seeds at 30 % plus the main run (median 2.16 ns, worst 2.27 ns). The Kc2-only unit has 3 seeds plus the main run (median 2.62 ns, worst 2.89 ns), and it is correctly stated to bind the Kc2 clock under the rule-B tree. `L3_laneclk` is priced at the median, with a new `_worst` variant. Max-Cut L2 is 0.924 / 0.926, still labelled tie / fragile. No Stage 4 verdict changes.

C1-C6: PASS. **Not accepted**: one fix, mechanical and cheap.

1. The remaining ladder columns and the analog corners still use the main-run restart rows, while the re-priced columns use the seed medians. That is two sources for one quantity. The effect is below 1 % and binds no clock under rule A, but the re-pricing is offline (`scripts/hw_timing/reprice_v2.py` over the stored Stage 3 / 4 records), so a full result should not carry the mismatch. Fix: re-run `reprice_v2.py` for every variant and the 15 analog corners x 2 stages, all using the median restart rows. Commit the regenerated `h6_*` / `h7_*` outputs, and add a test that every variant reads the same restart-row source.

Once that re-pricing is committed and its outputs differ from the current ones only within the stated <1 % (no verdict or label change), this track is accepted without a further review round.


## Re-check 4 close-out

accepted (conditional on 74d40e2 item, satisfied by the commit that adds this line): all variants (ladder, annotated, analog 15 x 2) were re-priced with the median restart rows; no verdict, label, scale verdict or ETS ratio changed (largest relative change below 5e-5); the same-source test passes. Max-Cut L2 stays labelled tie / fragile.
