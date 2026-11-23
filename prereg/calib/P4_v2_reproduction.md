# P4_v2 prereg: baseline faithfulness, published-figure reproduction, equal tuning (BASELINES_V2) — TOLERANCE FILE

Written 16 Nov 2026 (IST) and committed alone, before any scored run of the experiments below. P4.02 / P4.02a / P4.04 /
P4.05 / P4.06 stay as they are (their verdicts are history). The runners are `scripts/baselines/repro_v2.py` (R1-R4) and
`scripts/baselines/retune_v2.py` (R5-R6); both refuse to run unless this file is committed unchanged and print its
sha256 in every RESULT line. Covers checklist A1-A8.

Disclosed pre-registration observations (scratch, not scored, made while diagnosing; they motivated this file):
(a) Stage 4 raw: B3 records end at 28-35 conflicts on p3n240 with flips = steps; (b) one p3n240 instance (801), 30 sweeps,
4 seeds: B3 == ours.none at schedule fraction 1.0 (35 = 35), ours.none at fraction 0.5 reaches 2; B3 lin-beta with
T_low = p05/{1,2,4,8} ends at ~33 / 15 / 3 / 1 conflicts. Nothing below is tuned on these numbers; the R5 grid values are
fixed by the equal-search-space rule in section 5, not by (b).

## 0. Papers re-read (sources; deviations are listed in docs/hw/results/BASELINES_V2.md)
- B1: Yin et al., Nat. Commun. 15:2419 (2024), PMC10948773 + SI (sheet docs/hw/lit/yin2024_supp.md). MESA: each epoch starts
  from the previous epoch's optimum; proposals = "flipping a few bits"; a trap counter grows while the energy stays
  stagnant; at Count_max the epoch ends and T resets. Not published: schedule, Count_max, few = ?, iteration meaning.
  Hardware: one proposal per iteration, energy from one array read (x^T Q y), no parallel trial, no select tree.
- B2: Qian et al., HyCiM, arXiv 2410.14111v1. Filter success 98.54 % (Sec. 4.3), 40 Billionnet-Soutif n = 100,
  1000 initial states x 100 runs x 1000 iterations, success = profit >= 0.95 opt.
- B3: Aramon et al., arXiv 1806.08815v3. Gen-1 DA, annealing mode (no replicas; the PT-DA is a separate machine, PT moves on
  a CPU, not the benchmarked DA). 100 runs from x = 0, linear-in-beta schedule updated every iteration, offset OFF,
  Table I temperatures (SK-bimodal Th/Tl = 40/4; SK-Gaussian 2e5/1e4 with J ~ N(0,1) x 1e5), anneal length optimised per
  size (App. A: "number of sweeps for which the TTS distribution has the lowest mean"), Jeffreys Beta(0.5,0.5) posterior for
  the success probability, reference = exact (n = 64) or PT 5e5 sweeps. Fig. 2: constant-T, 1e5 sweeps thermalisation,
  5e3 sweeps measurement, N = 64, 100 instances x 10 repeats; Pp/Ps -> N at low T, -> 1 at high T.

## R1 (A1). B1: Yin SI Fig. S7 (MESA vs conventional SA on Gset1, 800 nodes)
- Machine: `yin_mesa.yin_native_run` (numba), Yin's native move set: per iteration ONE proposal flipping m distinct
  uniformly drawn bits, m uniform in {1, 2, 3} ("a few bits"), exact dE from the field, Metropolis accept.
- SA arm: geometric T0 -> T_end over the whole budget, no epochs. MESA arm: epochs; each epoch starts at the best state so far
  (the "previous optimum"), T := T0 and falls geometrically to T_end over E = 10 sweeps, then is held; the trap counter counts
  consecutive iterations with no strict improvement of the epoch-best energy and only runs once T has reached T_end
  (so an epoch can never end before it has cooled: K >= epoch, A2); at Count_max = 2n the epoch ends.
- T0 / T_end = 85th / 5th percentile of nonzero single-flip |dE| over 32 uniform random states (P4.02 rule), both arms.
- Instance G1 (registered); G2-G5 reported, not scored. Budget 1200 sweeps (Fig. S7a x-axis length, iteration read as a
  sweep = n proposals). 40 seeds per arm (common seeds). Solved = cut >= best-known (G1 11624), best-so-far.
- Targets: S_MESA = success at the end of the budget; S_SA likewise; TTS99 = min_t t R99(p(t)) (P4.02 definition, p(t) on
  the 40 seeds, evaluated every sweep). PASS iff (i) S_MESA >= 0.90 (paper 100 %, tol 10 pp), (ii) S_MESA >= S_SA (paper
  100 % vs 90 %), (iii) TTS_SA / TTS_MESA in [1.0, 4.0] (paper ~2x, factor-2 tolerance as PLAN "TTS within x2"); an
  undefined TTS fails (iii). Output `RESULT P4v2 R1 PASS|FAIL`.
- "+27 %" (Fig. 4b) is NOT scored: Yin's SA budget is unpublished, and any budget chosen to hit +27 % would be fitted.
  Report-only: MESA vs SA mean-cut improvement on G48-G50 (3000 nodes) at 10, 30, 100 sweeps, 10 seeds.

## R2 (A3). B3: Aramon Fig. 2 (parallel-trial acceptance boost)
- Machine: `fujitsu_da.da_const_t` (numba kernel of P4.03's B3 algorithm; equivalence to the golden B3Machine is a test),
  constant T, offset off, start x = 0, thermalise 1e5 sweeps, then measure 5e3 sweeps; at every measured iteration
  Ps = (1/N) sum_i A_i, Pp = 1 - prod_i (1 - A_i), A_i = min(1, exp(-dE_i / T)) (Eqs. 1-2); R(T) = mean Pp / mean Ps.
- N = 64, SK-bimodal (J = +-1) and SK-Gaussian (J = round(10 N(0,1)); paper's T axis scaled by 10 / 1e5); 20 instances x
  2 repeats (paper 100 x 10). T grid: bimodal 0.1, 0.3, 1, 3, 10, 30, 100, 1000; Gaussian = 1e-4 x (1e3 ... 1e8) in the same
  decades (0.1 ... 1e4).
- PASS iff for both classes: R(T_min) >= 0.9 N = 57.6 and R(T_max) <= 1.2 and R is non-increasing in T up to 5 % noise.
  `RESULT P4v2 R2`.

## R3 (A3). B3: Aramon Sec. VI.B TTS scaling exponent, paper methodology
- Kernel `fujitsu_da.da_anneal` (numba, same algorithm, linear-in-beta from Th to Tl over the run, T updated every
  iteration, offset off, x0 = 0). Th/Tl = Table I: bimodal 40 / 4; Gaussian 2e5 / 1e4 scaled to sigma = 10: 20 / 1.
- Sizes 64, 128, 256 locally (paper 64-1024; 512 and 1024 are the cloud job in BASELINES_V2.md under the same rule);
  20 instances per (class, n) (fujitsu_da.sk_qubo, i = 0..19); anneal lengths L in {25, 50, 100, 200, 400, 800} x n
  iterations; 50 runs per (instance, L).
- Reference E*: the best over every run of every L plus 10 reference runs of 4000 n iterations (self-referenced; paper uses
  exact/PT). theta = Jeffreys posterior mean (y + 0.5) / (r + 1); TTS_i(L) = L R99(theta).
- L* = argmin over L of mean_i TTS_i(L); TTS80(class, n) = 80th percentile over instances of TTS_i(L*).
  beta = least-squares slope of log10 TTS80 vs n. PASS iff beta in [beta_paper / 2, 2 beta_paper] (bimodal 0.00105-0.0042,
  Gaussian 0.00095-0.0038) for both classes. `RESULT P4v2 R3`. (The P4.04 failure used a fixed L = 400 n with an optimal
  stopping time, the percentile T rule, and a 64-256 fit; those are the deviations this tests.)

## R4 (A5). B2: HyCiM filter success (Sec. 4.3, 98.54 %)
- B2 kernel (hycim.py, v3 settings: S4 schedule, 50 % swap / 50 % flip, feasible_random init), the HyCiM filter at sigma = 0
  (exact by P4.06 A1). All 40 instances, 100 initial states x 10 runs, L = 1e5 proposals (= 1000 sweeps of n = 100, the
  registered reading of "1000 iterations"); per-run success = best feasible profit >= 0.95 opt.
- PASS iff the 40-instance rate is in [93.54, 100] %. Report-only: the literal 1000-proposal reading, same runs design.
  Label: v3 settings were chosen in the reference software study with the paper number in view (REPRO_RESULT_v3); stated, not hidden.
  `RESULT P4v2 R4`.

## 5. Equal tuning rule (A6), applied to every hardware machine
Every tuned hardware arm (ours, B1 none / MESA v2, B3 v2, B2) gets exactly **8 configurations = 4 shared (T_start, T_end)
percentile pairs {(85,5), (90,5), (85,10), (75,5)} x 2 values of one machine-specific secondary knob** (B2: its 4 schedules
x pswap, as in Stage 2), on the **same TUNE split** (plan.TUNE_SET) with the **same seeds** (TUNE_SEEDS = 2) and the **same
selection rule** (evaluate_h2.select_tuned: lowest mean normalised gap at the end of the budget, ties by energy).
Search space parity: ours' "none" knob (schedule fraction 0.5) reaches a final temperature T_end^2 / T_start because the
geometric schedule keeps cooling after T_end; B3 v2's knob is therefore the final temperature of its linear-in-beta
schedule, T_final in {T_end, T_end^2 / T_start}, so ours and B3 v2 search the same (T_start, T_final) set. B1 MESA v2's knob
is Count_max in {n, 2n} (as ours' stall arms); its epoch length is fixed at 10 sweeps (P4.02a value, not tuned).

## R5 (A4, A6). Re-tune B3 v2 and B1 MESA v2 under section 5
- Arms `b3.b3v2` (offset off = paper's final setting, lin-beta, knob T_final) and `b1.mesa2` (MESA v2 on the shared parallel-
  trial golden machine: epoch cooling, hold, trap counter after cooling, epoch restart from best + m in {1,2,3} bit kick).
  Tune on all Stage 2 TUNE families (maxcut, maxsat, colouring) exactly as Stage 2 did; selection by select_tuned.
- Output: tuned.json for these two arms (sim/out/hw/baselines_v2/tune/).

## R6 (A4). Does B3 solve colouring? (Stage 4 240-spin TEST, re-run of the two new arms only)
- p3n240 and p4n240 TEST instances and seeds exactly as Stage 4 (plan_h7; ideal device, 150 sweeps), arms b3.b3v2 and
  b1.mesa2 with the R5 tuned configs (and, report-only, b3.b3v2 at the T_final = T_end^2 / T_start knob if R5 selects the
  other value, labelled post-selection). Success = proper colouring (energy 0).
- PASS (A4 "B3 solves colouring") iff B3 v2 success >= 10 % on at least one of the two families with Wilson 95 % lower
  bound > 0. Contrasts vs the frozen Stage 4 ours numbers are reported, not re-scored as H7 verdicts (H7 is closed).
  480-spin families and DIMACS: cloud job (BASELINES_V2.md). `RESULT P4v2 R6`.

## 7. Per-machine clock (A7)
B3 (DA) keeps the N-wide uniform select (Aramon Alg. 2), so its clock = max(select tree at its padded N, B3 lane path); the
B3 lane is synthesised with the shared timing study v1 flow at the DA widths (JW = 16, BW = 26, HW = 32, EW = 26). B1 (Yin) has one
proposal per iteration and no select tree: clock = its lane path (Metropolis + field compare; tile sums are already extra
cycles in pricing). Rows go to docs/hw/energy_table_baseline_clock.csv; MeasuredCost gains baseline_clock = "own" (minimal
shared hook). Stage 4 ETS99 ratios are re-priced offline under "own" as a sensitivity (no verdict change is claimed in
advance; H7 verdicts are not re-scored).

## 8. Cost rule (A8)
One test module asserts, for every machine (ours, B1, B2, B3) and every table name in cost_model.TABLES (canonical,
measured_v1, and measured_v2 automatically when it is added), that ADC bias is charged per step on every machine with an
ADC, tiles scale conversions, and B3 has no ADC/array charge.

No knob, tolerance, size, seed count or instance list above may change after this file is committed. A FAIL is reported as
a FAIL with its label ("B<k> <figure> not reproduced under the P4_v2 reading").
