# H8 prereg: full hardware comparison (where each machine wins, and how far it scales)

**FROZEN by this commit (20 Nov 2026 IST), before any H8 raw record exists, after independent internal review of every component. Untagged. No H8 compute has run; the smoke runs
(1 sweep, `sim/out/hw/h8_smoke`) are plumbing checks, never data.
Code that implements it: `scripts/testing/{plan_h8,h8_instances,gen_jobs_h8,run_h8,evaluate_h8}.py`, `scripts/cloud/h8/*`, `tests/hw/test_h8.py`.
Design rationale, costs and the internal review: `docs/hw/results/H8_DESIGN.md`. Earlier preregs (H0-H7, P4_v2) are not changed.

## 0. Status of the question (read first)
Settled inputs (their checkers are accepted or nearly accepted): hardware pricing `measured_v2` (pipelined select tree, median / worst clocks, restart cycles
priced; TIMING_PIPELINE_V2.md), device variation (VARIATION_V2.md: realistic sigma, mitigations under one rule, restore claims conditional on an unmeasured
C2C share >= about 0.25 for ours and 0.5 for B1; B2 is not restored), baselines (BASELINES_V2.md: faithful B1_yin, B3 v2 per Aramon, equal tuning rule).
Key finding that this study must test at scale, not assume: properly tuned B3 (digital annealer) beats ours Kc2 + I11 on planted 3-colouring in energy
(ETS99 ratio ours / B3 2.6 at 240 spins, 7.9 at 480) and success; ours wins DIMACS-style graphs (0.008) and is the only machine solving 4-colouring.
The fairness arm ours.kc2c (Kc2 with B3's T_final knob) is pending a cloud tuning run; its slot in this design is a hook (section 4.3).

## 1. Hypotheses (all contrasts are energy-to-solution ETS99 ratios unless stated; < 1 favours the first arm)
- **H8-A (primary, per family, nominal condition).** For every family cell of section 3: (a) ours_kc2_i11 vs B3_v2 and (b) ours_kc2_i11 vs B1_best.
  Verdict classes: win / tie / loss / inconclusive / not evaluable (rules of H2 section 6 / evalcommon: win needs ratio <= 0.95, Holm-adjusted p < 0.05 and a
  success difference not worse than -1 pp; not evaluable if the comparator is at 0 % success).
  The **global** Holm family is the 2 x (number of family cells) primary contrasts at the nominal condition: m = 20 in CORE (8 planted + generated graphs + G1000 = 10 cells), m = 26 in
  FULL (+ p3n2040, p4n2040, G2000). The primary verdict (the `energy` column of the report, field `energy`) uses the GLOBAL adjusted p (`holm_p_global`); the per-cell Holm over the 6
  registered contrasts of the cell (`energy_cell`) is secondary and is the verdict only for non-primary contrasts (ideal condition, ours_none, kc2c, ladder). An incomplete family
  (fewer primary contrasts present than m) is flagged in the report and carries no headline verdict.
- **H8-B (scale).** For each machine and condition: success and ETS99 against spins (p3 / p4 planted 120 / 240 / 480 / 960 [/ 2040], G-set 1000 [/ 2000]),
  the log-log ETS99 slope over the sizes with success > 0 (reported only with >= 3 points), and the largest size with success >= 0.5 and >= 0.1. Descriptive
  (no test): the question "how far does it scale" is answered by these curves and by H8-A at every size.
- **H8-C (mitigation tax).** ours_kc2_i11 nominal (with wv + diff + cal) vs ours_kc2_i11 ideal, B1_best nominal (wv + cal) vs ideal: the energy and success
  cost of surviving the device variation. Report-only.
- **H8-D (ablation ladder with mitigations).** The H2 ladder rungs re-run with the chosen mitigation stack on p3n240 / p4n240 (ideal and nominal) and the
  G-set 1000 group (nominal): none, DA offset, MESA, Kc2, Kc2 + I11, Kc2 + I7v2 + I11, Kc2 + I7v2 + I10 + I11, Kc2 + I5. Contrasts: each rung vs the previous one
  and vs `none`; Holm per cell. I3 (penalty ramp) is knapsack-only and has no colouring / Max-Cut arm: recorded as not applicable. I10 enters only through
  the I7v2i10 rung (the fs-ADC arms are lossless by construction).
- **H8-E (variation stress, report-only).** At the design point (p3n240, p4n240): success against k (all variation terms x k, k = 0.5, 1, 1.5, 2, 3), against the
  C2C share (0, 0.25, 0.5, 0.75 at k = 1 and 2), against drift (0.01, 0.02, 0.05 V per decade, parametric: the retention fit is k = 0 in char_v1) and unmitigated
  at k = 1, for ours_kc2_i11 and B1_best with their chosen mitigation (B1 also wv + diff + cal + bin at k = 3). Newcombe difference to the ideal device; a cell is
  "restored" if the lower bound of (success - ideal success) >= -0.10. Every statement is conditional on the unmeasured C2C share.
- **H8-F (software context, no energy claim).** DSATUR, TabuCol (iterations per vertex = the sweeps of the family) and SA (dwave-samplers, same QUBO, same sweeps)
  success on the same instances and budgets; 20x TabuCol solvability of every colouring instance (3 seeds). Software CPU seconds per run are printed as context
  and are never a hardware time or energy. A software-energy estimate is NOT made (no defensible per-operation energy for a vCPU on a shared cloud host).

## 2. Machines and conditions
| label | spec arm | config source | chosen mitigation at nominal | note |
|---|---|---|---|---|
| ours_kc2_i11 | ours.kc2.fs.i11 | Stage 2 tuned colouring / Max-Cut key ours.kc2.i10.i11 | wv + diff + cal | primary ours |
| ours_none | ours.none.fs | ours.none.i10 | wv + diff + cal | restart-free ours (the L2 cost-only effect) |
| B1_best | b1.none.fs | b1.none | wv + cal (B1 at k = 1; bit-sliced wv+diff+cal+bin only at k = 3 in the stress) | strongest B1 reading (parallel-trial core, no restart) |
| B3_v2 | b3.b3v2 | baselines_v2/tuned.json b3.b3v2 | none (digital) | Aramon DA, lin-beta, T_final knob |
| ours_kc2c | ours.kc2.fs | baselines_v2/tuned.json ours.kc2c (pending) | wv + diff + cal | fairness arm, section 4.3 |
| B1_yin_sa | b1y.sa | baselines_v2/tuned.json b1y.sa | none | context only, ideal device, 120 / 240 spins (solved nothing at 150 sweeps in P4_v2 R6) |
B2 (HyCiM) is QKP-only (BASELINES_V2 3b): it has no colouring or Max-Cut formulation here and is excluded; this is stated, not a silent omission.
Conditions: **ideal** = no variation, no mitigation (what the machine would do on a perfect device; B3 is digital and has only this one condition and
serves as comparator in both); **nominal** = every stochastic variation term at x1 (VARIATION_V2 `vx1`: D2D, C2C share 0.5, read noise, ADC offset) with the
machine's chosen mitigation, simulated by `PerturbedCimV2` (ADC rounding and clipping under noise are real). No tuning is done in H8: every config is a frozen
earlier selection (tuned on Stage 2 / P4_v2 TUNE instances, 8 configs per arm, one rule). A machine whose tuned config does not transfer to a family is
reported as it is; no re-tuning "for H8" (that would break the equal-effort rule A6).

## 3. Instances, seeds, budgets (fresh, disjoint from every earlier stage)
Seed stream: `Spec.tag = 9`, `inst_index = 500 + position` (Stage 2: tag 0, Stage 3: 6, Stage 4: 7, VARIATION_V2: 8, inst_index 100 / 300 / 400+).
Planted colouring (h6 generator, H6 degrees: p3 = 3-colourable, expected degree 4.5; p4 = 4-colourable, degree 8; optimum energy 0 by construction):
p3 seeds 1101.., p4 seeds 1201.. (earlier seeds: 301-310, 401-404, 501-503, 801-810, 851, 901-910, 951). Generated graphs from their definitions (no file, no
licence): queenN_N (N = 5..10), mycielK (K = 4..7), Kneser graphs KG(N, K) with chi = N - 2K + 2 (Lovasz 1978; 7_2, 8_3, 9_3, 10_3, 10_4), k = chromatic number.
DIMACS benchmark files that need a download (le450, DSJC, flat, school, ...) are NOT used: licence / redistribution is not confirmed; adding them is an author
decision. Max-Cut: Stanford G-set, best-known cut from the vendored CSV, success = cut >= 0.99 x best-known; instances G51-G54 (1000 nodes, unweighted planar) in CORE and G27-G31 (2000 nodes, +-1 random) in FULL.
**All 800-node G-set graphs are NOT fresh** (Stage 2 TUNE/TEST G1-7 G11-16 G18; Stage 3 / H6 TUNE G9 G20, TEST G8 G10 G17 G19 G21; P4.02 B1 calibration G1-G17, G22-G26, G43-G47, G48-G50;
P4_v2 R1x G48-G50), so no 800-node Max-Cut cell exists in H8; G22-26 and G43-47 are also excluded (P4.02). G27-G42 and G51-G54 appear in no earlier plan; `tests/hw/test_h8.py`
recomputes the exclusion from Stage 2, H6, H7, the P4.02 / R1x calibrations and VARIATION_V2, and checks the mixed seeds of all earlier specs against every H8 seed.
| family | spins (lanes) | sweeps | CORE instances x seeds | FULL instances x seeds | MDE success diff (core, m=20 / full, m=26) |
|---|---|---|---|---|---|
| p3n120 / p4n120 | 120 (128) | 150 | 40 x 8 | 48 x 10 | 0.20 / 0.18 |
| p3n240 / p4n240 | 240 (256) | 150 | 36 x 6 | 44 x 8 | 0.23 / 0.20 |
| p3n480 / p4n480 | 480 (512) | 300 | 18 x 5 | 24 x 6 | 0.33 / 0.28 |
| p3n960 / p4n960 | 960 (1024) | 600 | 10 x 4 | 14 x 5 | 0.45 / 0.38 |
| p3n2040 / p4n2040 | 2040 (2048) | 600 (cap) | - | 4 x 2 | 0.75 (trend only) |
| generated graphs (core: myciel4-6, queen5_5-9_9, kneser7_2 8_3 9_3; full adds myciel7, queen10_10, kneser10_3 10_4) | 105-1528 | max(150, 150 x spins / 240), cap 600 | 11 graphs x 8 | 15 graphs x 12 | per graph shown |
| G-set 1000 (G51-54) / 2000 (G27-31) | 1000 / 2000 | 150 | 4 x 6 / - | 4 x 8 / 5 x 2 | per cell in the report |
Budget scales with N at the H7 per-spin rate (150 x N / 240), floor 150, cap 600 (a 2040-spin B1 run at 1275 sweeps would exceed the 60 min job limit; the cap
applies to every machine equally and is stated as a limitation: at 2040 spins every machine runs fewer sweeps per spin than at 960). Stress: p3n240 / p4n240,
first 10 instances x 6 seeds per point. Ablation: p3n240 / p4n240 first 10 x 5 (ideal and nominal), G1000 first 3 x 4 (nominal). B1_yin_sa: first 12 x 4.

## 4. Pricing
### 4.1 Primary
`measured_v2` L3_v2 (`MeasuredCostV2()`: pipelined select tree at the cut mask of each padded N, per-machine clock = max(tree, lane, RNG, restart unit),
median over the N = 1024 P&R runs, restart cycles priced, idle energy of every machine under one rule, gated generators, B1 / B3 on the same-tree clock) plus the
mitigation overhead of the run, priced with the same table through `variation_v2.mitigation_cost` (runtime overhead as a factor on cumulative energy and time;
extra area added to the arm's area; one-time programming + calibration energy charged to EVERY run, the conservative deployment-per-run reading). Verdicts use only this.
### 4.2 Sensitivities (reported next to every primary verdict; a flipped verdict is flagged, the primary is never changed by it)
canonical table; baselines on the lane-path clock; ungated generators (RNG_CG = 0); worst N = 1024 clock; 20 ns analog settle; one-time mitigation energy dropped.
N > 1024 lanes (2040-spin colouring, 2000-node Max-Cut) are priced by log-log extrapolation of the measured block table (measured N = 64..1024): those cells carry
`extrapolated_N = true`, are never used for a headline verdict without the label, and become measured only after a new N = 2048 P&R.
### 4.3 ours.kc2c hook
`plan_h8.kc2c_ready()` is true when `docs/hw/results/baselines_v2/tuned.json` holds `tuned.colouring['ours.kc2c']` and `tuned.maxcut['ours.kc2c']`. Then the
arm joins H8-A (ours_kc2c vs B3_v2, ours_kc2_i11 vs ours_kc2c) and the main TSVs automatically; before that the arm has no rows, the payload ships the add-on TSVs
`jobs_h8_{core,full}_kc2c.tsv` (rebuild the payload after the selection is committed, run `go_h8.sh core-kc2c`), `run_h8.py` REFUSES the arm if its selection is missing,
and the report prints `kc2c_arm: PENDING`. Adding the arm does not change any other job id.

## 5. Statistics
Success = reaching the target energy (0, or -0.99 x best-known cut) at the end of the budget; ETS99 / TTS99 pooled over instances with the two-level paired bootstrap
(instances then seeds, B = 10000, seed 20261116) on shared resamples, exactly as H2 / H7 (`evalcommon`); Holm as above; contrast verdict margins +-1 pp and 5 %.
Planned statistics are computed on the complete (instance, seed) rectangle common to every arm of the contrast; incomplete rectangles are reported, not pooled.
Power: normal approximation for the paired success difference with intra-instance correlation rho = 0.25 (the largest of the 0 to 0.25 estimated from Stage 4
records), arm correlation 0.5, Bonferroni worst case alpha / m with m = the global Holm family of the tier (20 core, 26 full): the table in section 3 is the minimum detectable SUCCESS
difference at 80 % power (the verdict test itself is the ETS99 bootstrap p, not this normal approximation). Effects below it are
reported as "not resolved", never as ties. Where the expected effect is large (a machine at 0 % against 50 %), the design is adequate; the 960 and 2040 cells
resolve only large gaps and say so.

## 6. Tiers and cost (Rs 64.28 / h, 32 vCPU, IN1; Rs 2.01 per vCPU-h; tail factor 1.15; typical set-up 0.25 h and gate 0.15 h; every phase hard-timed)
CORE: 80.1 CPU-h (88.3 with ours.kc2c), 442 jobs (+ 44 for kc2c), longest job 25 min, estimated Rs 211 (Rs 230 with kc2c), 3.3-3.6 h wall including typical set-up and gate. **Guaranteed ceiling
Rs 295**: `go_h8.sh` hard-times set-up (20 min), gate (tests 10 + smoke 15 min; the core gate smokes only CORE job types), scheduler deadline 205 min + 20 min kill window and collection (5 min) = 275 min.
FULL = CORE plus the extra pairs and the 2040-spin / 2000-node / extra-graph cells: +111 CPU-h (+122 with kc2c), +Rs 256 (+Rs 283), longest job 48 min; full total about Rs 467 (Rs 512) with its own
(full-types) gate. Per-run seconds come from the measured Stage 4 cloud wall times (ours 1.8 / 10.2 s,
B1 7.2 / 52 s, B3 1.5 / 6.8 s at 240 / 480 spins), power-law extrapolation in lanes, mitigation factors 1.45 (ours) / 1.55 (B1) from the VARIATION_V2 wall times, x1.3 margin.
Peak host RSS of a mitigated analog job is dominated by the (32-attempt) programming arrays (5.0 GB measured for ours at 960 spins; up to 51 GB declared for the
largest graph at 2048 lanes): the scheduler admits jobs by declared RSS against 0.85 x MemTotal.

## 7. Decision rules for the paper (what the evaluator output may be turned into)
A "win" is allowed to be written only for a cell whose primary global-Holm verdict is win AND whose sensitivities do not flip it (flags are quoted if they do);
"ours wins family F / loses family G" statements carry the nominal-condition verdict and the ideal-condition verdict side by side; scale statements cite H8-B curves
with the size at which success crosses 0.5 / 0.1; every variation statement carries "conditional on the unmeasured C2C share (>= 0.25 for ours, >= 0.5 for B1)";
a cell with `extrapolated_N` carries "N > 1024 priced by extrapolation". Nothing is pooled with Stages 2-4.

## 8. Known limitations (stated now, not discovered later)
Absolute energies come from stand-in BSIM4 / FreePDK45 models (ratios only, about x2); B1 and B3 were never synthesised (same-tree clock rule, with the lane-path sensitivity);
the mitigation costs are a one-rule model, not silicon; C2C share, drift and retention are unmeasured; no process-corner card exists; the budget cap at 2040 spins; a
tuned config chosen on 120-240-spin instances is applied unchanged at larger N; B2 excluded; software energy not estimated; I3 not applicable.
