# TIM v0 RTL: status

Last update: 31 Oct 2026 (IST). Branch `fx-rtl0`. Spec: `docs/rtl/SPEC_v0.md`. Run all tests:
`scripts/run_rtl_tests.sh` (about 4 minutes when the guard slots are free; add `--long` for the N = 256 run).

## What exists

| Part | Files |
|---|---|
| Spec (widths, cycles, rules, address map, file formats) | `docs/rtl/SPEC_v0.md` |
| Golden model, integer and bit-exact | `scripts/golden/tim_golden.py` (machine, RNG, LUT, pricer, transition matrix, file I/O), `scripts/golden/instances.py` (QUBO, Max-Cut, D5c generator port, register conversion, brute force) |
| Golden self-test | `scripts/golden/selftest_golden.py` |
| RTL (Verilog-2005, 17 modules) | `rtl/src/`: `tim_top`, `tim_ctrl`, `tim_lane`, `coupling_mem`, `field_unit`, `spin_reg`, `accept_lut`, `accept_unit`, `select_tree`, `offset_unit`, `temp_sched`, `xoshiro128ss`, `splitmix64`, `constraint_unit`, `query_enc`, `tcam_stub`, `seg_adder` |
| Testbenches | `rtl/tb/`: 9 unit testbenches and `tb_top.v` |
| Test generation and checks | `scripts/golden/gen_tests.py`, `check_top.py`, `compare_trace.py` |
| Runner | `scripts/run_rtl_tests.sh` (every simulator and Python call goes through `scripts/run_guarded.sh`) |
| Integer vs float ranking check | `scripts/golden/d5c_rank_check.py` |
| Example instance file | `sim/data/ring8.inst` (format: SPEC 9.1) |

## Machine summary

- Parallel-trial annealer, N lanes (default 64; elaborates and runs at 8, 16, 64, 256). QUBO / Max-Cut mode and a
  knapsack mode whose hinge penalty comes from two TCAM searches per step (ADD with rows ¬x enabled, REM with rows x
  enabled), D5c thermometer code, m = 8 constraints × Q = 8 levels = one 64-cell segment (Q = 16 uses 2 segments).
- Acceptance: geff + E_off + (T·L[u_top]) >> 24 ≥ 0, L = −ln u from a 1024-entry LUT; per-lane xoshiro128\*\*
  seeded by a splitmix64 shift chain; uniform pick of one accepted lane by a count-tree walk; E_off grows by ΔE when
  nothing is accepted; global T with a per-step geometric schedule or hold.
- **Bit widths:** P 8 signed, d 8 signed, w 6, C/load 16, slack 17, field h 18 signed, f 32 signed, Λ 16, count 7
  per segment, E_off 24 (saturating), ΔE 16, T 32 (UQ16.16), α 32 (UQ0.32), LUT entry 12 (UQ4.8), θ 20,
  acceptance sum 28 signed. Energies in eLSB = 2^−gsh units of f (gsh = 0 for QUBO, log2 Q for knapsack).
- **Cycles per step:** 4 in QUBO mode; 7 + 2·SEARCH_LAT in knapsack mode (11 at the default SEARCH_LAT = 2).
  Start-up: 2(N+1) seeding cycles + 1 init cycle. Checked on every step of every top-level run.

## Test results

Full run `scripts/run_rtl_tests.sh --long`, 31 Oct 2026 about 04:50 IST: **24 of 24 passed**, no compiler warnings.
Times include waiting for a guard slot (other sessions were running ngspice).

| Test | Result | What it showed |
|---|---|---|
| golden_selftest | PASS | 12/12: splitmix64 equals the reference software study; pricer counts equal the qkp_nb float formula (n = 40/64/200, Q = 8/16); D5c generator port equals the reference software study |
| tb_rng | PASS | 10 splitmix64 outputs, 5 chain-seeded states, 320 xoshiro128\*\* outputs equal golden |
| tb_select | PASS | 882 432 checks; 6 patterns exhaustive over all 2^16 r16 at N = 16 and 64 |
| tb_accept | PASS | 40 008 checks against a 64-bit reference (incl. sum = 0 accepts, −1 rejects, extremes) |
| tb_field | PASS | 3000 random flips at N = 16, every field equal to d + P x; overflow flag rises when forced |
| tb_coupling | PASS | 64 words, 500 random registered reads |
| tb_offset_temp | PASS | 5000 offset updates (694 saturated); 3 × 2000 schedule steps; hold |
| tb_tcam | PASS | 500 searches at latency 3 and 1; 41 writes, 1 dropped; counters; 818 injected ±1 errors, all bounded and counted |
| tb_pricer | PASS | 23 040 row counts at Q = 8 (1 segment) and Q = 16 (2 segments) equal the hinge formula |
| tb_constraint | PASS | 3000 flips; feas_next right on 544 feasible and 2456 infeasible after-flip states |
| elab_n16 / n64 / n256 | PASS | `tim_top` elaborates, 0 warnings |
| ring8 | PASS | example file `sim/data/ring8.inst`; bit-exact 300 steps; best 8 = optimum |
| qubo64 | PASS | bit-exact 1500 steps |
| maxcut16 | PASS | bit-exact 3000 steps; best 40 = brute-force optimum |
| torus64 | PASS | bit-exact 6000 steps; best 128 = optimum |
| knap16 | PASS | bit-exact 4000 steps through the TCAM; best 610 = brute-force optimum, feasible |
| knap16_lat1 / lat3 | PASS | same trace at SEARCH_LAT 1 and 3; 9 and 13 cycles per step |
| knap16_q16 | PASS | Q = 16, two TCAM segments; bit-exact; best 610 = optimum |
| knap64 | PASS | bit-exact 1500 steps, n = 64, m = 8 |
| trans8 | PASS | bit-exact 40 000 steps; RTL transition frequencies vs exact DA matrix: chi-square 576 on 613 dof, p = 0.85 (248 of 256 states visited). The wrong model (lowest-index pick) is rejected because it gives probability 0 to transitions the RTL makes (a crude but valid rejection). DA stationary distribution vs Boltzmann at the same T: total variation 0.072 (the DA chain is not Boltzmann, as expected) |
| qubo256 (long) | PASS | N = 256 elaborates and runs 40 bit-exact steps (62 s, mostly 65 536 coupling writes) |

**Do the tests catch bugs?** Three one-character mutations of the RTL (in a copy under `sim/out/mut/`) were each
caught by knap16: acceptance `≥ 0` changed to `> 0` (first difference at step 1281), the tree walk `<` changed to `≤`
(step 1), the ADD mask `<` changed to `≤` (step 3).

The schedules and step counts of the "best = optimum" tests were fixed before any RTL run; the golden model reached
the optimum with them, and the RTL, being bit-exact, reports the same.

## Integer golden model vs the reference software study's float model (D5c ranking, direction only)

Script: `scripts/golden/d5c_rank_check.py` (run under the guard with `-I`; reads the reference software study code and results, read
only). Cell n = 200, m = 16; the D5c-selected configs (HX `penalty|T3|lsc0.25`, HQ8 `qhinge8|T3|lsc0.25`,
HQ16 `qhinge16|T3|lsc0.25`, FI `filter|T10|de10`); test instances 5000–5004 × seeds 100–101 (10 paired runs per
arm), full budget 100 000 steps. Gap = 100·(best known − best_f)/best known, best known over both models.
Criterion fixed before running: every contrast has the same sign in both models.

| model | HX | HQ8 | HQ16 | FI |
|---|---|---|---|---|
| float (qkp_nb) | 0.428 | 0.661 | 0.426 | 3.898 |
| integer (golden) | 0.450 | 0.819 | 0.524 | 3.774 |

| contrast (positive = first arm worse) | float | integer | D5c full test (200 runs) | same sign |
|---|---|---|---|---|
| HQ8 − HX | +0.232 | +0.369 | +0.206 | yes |
| HQ16 − HX | −0.002 | +0.075 | +0.041 | **no** |
| FI − HQ8 | +3.238 | +2.955 | +3.634 | yes |

**Result: the criterion fails, 2 of 3 contrasts agree.** The disagreeing contrast is HQ16 − HX, where the float
model's estimate on these 10 runs is −0.002, essentially zero; the integer value (+0.075) has the same sign as the
D5c full-test value (+0.041), which D5c judged equivalent to zero. So the failure reflects a near-zero contrast, not
a reversal of a real effect, but by the pre-set rule it is a failure and is recorded as one. Also notable: the
integer model's TCAM arms are somewhat worse than the float model's (HQ8 +0.16 points, HQ16 +0.10), while HX and FI
are close; 10 runs cannot tell whether this is noise or a real effect of the LUT acceptance or the rounding of Λ.
hw_prior_art §1.4 asks for the integer model to reproduce the D5c ranking within the 0.17-point margin on the
stored tune/test seeds before RTL comparisons count; that larger check (all cells, more seeds) is G1 work and has
not been done.

## What is stubbed or simplified

- **TCAM:** `tcam_stub` is our behavioural, exact digital model (also the C2 digital-equivalent control). It has the
  hooks the FeFET array will need (search-latency and write-latency parameters, error-injection input, event
  counters), but its latency, energy and error numbers are placeholders until our SPICE runs (G4) exist. The error
  rule (count ± 1 with probability err_thr/2^16) is a stand-in for the per-level error table; the golden model does
  not model errors yet, so runs with `err_en = 1` cannot be compared bit for bit.
- **Visited-state TCAM (H4 control):** the stand-in stores ternary rows (care masks), so it can hold visited states,
  but there is no threshold-match output (`r_hit`), no write-at-stall logic and no lockout counter yet.
- **Controls:** C2 exists (the stand-in). C1 (TCAM off, area reallocated) and C3 (exact and adaptive digital hinge)
  are not in the RTL; the exact hinge and the exact filter exist only in the golden model (for the ranking check);
  the adaptive hinge exists nowhere in this project yet.
- **Schedule:** per-step geometric or hold only; no (T_k, N_k) staircase table.
- **Not pipelined:** one step at a time, no overlap of the next step's query encoding with the current update.
- **Host interface:** a plain write-only bus and a direct TCAM write port; no read-back, no AXI.

## Known gaps and risks

0. **Integer model not yet validated against D5c.** The direction check above failed its own criterion (2 of 3
   contrasts), and the integer TCAM arms look 0.1–0.16 points worse than float on 10 runs. The full gate of
   hw_prior_art §1.4 (D5c ranking within 0.17 points on the stored seeds) is open; until it passes, RTL results are
   not comparable to the reference software study's numbers.
1. **N must be a power of two and every lane is live.** A padded lane (d = 0, P = 0) has gain 0, so it always accepts
   and would be picked. The D5c science instances (n = 200) need N = 256 with a lane-enable mask. Not done.
2. **Max-Cut range:** with 8-bit d and P, weighted degree must be ≤ 127 and |w| ≤ 63 (P = −2w).
3. **LUT copies:** one 1024 × 12-bit LUT per lane is 12 kbit per lane (3 Mbit at N = 256): too big for a KV260.
   Options for G2: 256 entries, or the leading-zero-count + 16-entry form from hw_prior_art §1.4, or a shared table.
   Any change must go into the golden model first.
4. **One multiplier per lane** (T·L, 32 × 12) plus the Λ·count products; DSP use not yet counted.
5. **Synthesis not checked.** The code avoids non-synthesizable constructs (no initial blocks or delays in
   `rtl/src`), but without a synthesis tool nothing confirms it maps cleanly. The count-tree walk and the 64-bit
   splitmix64 multipliers are long combinational paths.
6. **Offset-on statistics:** the transition-matrix test runs with ΔE = 0 (then x alone is Markov). With the offset
   on, the state is (x, E_off); that test does not exist yet.
7. **Icarus speed:** about 2–4 ms per step at N = 64 (QUBO) and about 9 ms per step at N = 64 (knapsack). Long
   anneals (10^5 steps) at N = 256 are not practical in Icarus; the G1 cycle model or Verilator is the path for
   statistics.

## Open tool requests

- **Verilator** (faster simulation for long runs; the plan's G2 tool) and **Yosys** (synthesizability check and
  area/LUT estimates before G3). Neither is installed, and nothing was installed for this work.

## Next steps

- **G1 cycle model:** extend the golden model with the cycle counts of SPEC §4 and op/event counts per step (TCAM
  searches, enabled rows, evaluated cells, coupling reads), so G0 energy numbers can be charged per step.
- **G2 RTL proper:** lane-enable mask and N = 256 science configuration; pipelining (overlap QENC/SADD with UPD);
  staircase schedule; C1 and C3 controls in the same RTL; per-segment λ weights; the H4 visited-state mode
  (threshold match, write at stall, lockout counter); error injection from a SPICE error table, mirrored in the
  golden model; offset-on statistics test; synthesis with Yosys if approved.
- **G3 FPGA (later):** KV260 mapping, on-board counters, the same per-step trace compared bit for bit.


## P3 additions (hw phase, branch hw/p3-rtl, 15 Nov 2026 IST)

Spec: `docs/rtl/SPEC_v0.md` section 11. Run all: `scripts/run_rtl_tests.sh --long` (via the local job queue).

| Task | Added | Tests (all bit-exact against the golden model unless noted) |
|---|---|---|
| P3.01 | lane-enable mask (region 6), FIXES R1 | `lane200_256` (n = 200 in N = 256, 300 steps) |
| P3.02 | `restart_unit.v`, controller state S_RST: arms none / da_offset / mesa / kc2 (Kc2 per ruling R1) | `tb_restart` (88 805 checks: stall counter, mesa reload over all 65 536 state pairs, kc2 kick over 255 masks x 9 L x 3 restarts), `maxcut16_{kc2,mesa,none,da}` 3000 steps (56 kc2 and 93 mesa restarts) |
| P3.03 | `cim_field_unit.v` (array planes, b-bit ADC, shift-add, xorshift32 noise mirrored in `cim_field.py`), state S_CIM | `tb_cim_field` (2 x 3000 vectors, ADC 2-16 bits, with and without noise), `qubo64_cim` 1500 steps (5-bit ADC, sg = 2000) |
| P3.04 | `power_ctl.v`: I10 read skipping + ADC bias gating, I7 precision switch, 8 activity counters | `maxcut16_i7i10` and `qubo16_i10skip` (2310 skipped reads, 2303 gated steps): trace and per-step counters (cycles, reads, skipped, cells, conversions, bits, low-bit, gated) equal `OpCounters` |
| P3.05 | exact (x, E_off) chain (`trans_off.py`) | `trans8_off`: chi-square p = 0.069 on 17 dof; lowest-index selector and a no-offset model both rejected (p = 0). The chain reaches k = 2 only (16 (x, k) states visited) |
| P3.06 | d 12 bit, P 10 bit (FIXES R11); zero-initialised coupling arrays in simulation; sparse host scripts | `torus64`, `qubo64_wide` (|P| up to 500, |d| up to 2000), `gset800` (G1-like n = 800 plus a hub of degree 589 = G-set maximum, padded to N = 1024, 40 steps, 375 s, no overflow flag) |

Notes: the best-state shadow register of the MESA arm is the controller's existing `best_x`. Restart steps take extra
cycles (`rs_cycles`); the testbench checks cycles per step as base + restart + CiM cycles. The activity counters are the
power-related subset of the P2.06 counters; adds, RNG draws and register-write counts are not RTL-observable and stay in
the golden model.
