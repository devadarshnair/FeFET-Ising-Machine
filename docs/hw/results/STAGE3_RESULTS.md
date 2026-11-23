# Stage 3 (H6 confirmatory follow-up) results

Rules: prereg/hw/H6_followup.md + prereg/hw/H6_amendment1.md (both committed before any Stage 3 data). Run pin d2c7d25
(= fc2dd27 + pre-run review doc), cloud gate STAGE0_GREEN at that pin (tests/hw 357 passed, smoke_all, stage3 smoke incl.
select/report barrier). 198/198 jobs rc 0, 5880 TEST/TUNE records + H5 re-run. Return package
00_admin/cloud_cpu_return/20261116T190605Z_stage3_198of198/ (SHA256SUMS all verify; raw_outputs.tar.zst sha256 prefix
24cc17695cc8f808). All numbers are from stand-in BSIM4 / FreePDK45 cost models: ratios only, absolute values about x2 uncertain.

Eval tables: docs/hw/results/stage3_eval/ (h6_sweep.json, h6_report.json, h6_report.md).

## Checks done before reading
- **Evaluator reproduced exactly.** `evaluate_h6.py --select` and `--report` re-run locally on the unpacked raw data
  (sim/out/hw/stage3, gitignored): h6_sweep.json, h6_report.json and h6_report.md are identical to the cloud outputs.
- **Tuning/test split respected.** TUNE instances (Max-Cut G9, G20; col3p 601-604; col4p 701-704) have zero overlap with TEST.
  Each swept TEST arm ran exactly one config, equal to the h6_sweep.json selection made on TUNE records only.
- **Data sanity.** No NaN best energy, no non-positive or non-finite energy, no zero-flip run, no empty job file, no timeout;
  restart counts are present on every record. An earlier setup attempt at the pin was refused (Verilator missing), then passed;
  the gate ran after that.
- **Holm** applied as registered: 14 contrasts on Max-Cut, 12 per colouring family (L3 budgets are Max-Cut only).

## Verdicts per lead

| Lead | Contrast (TEST) | ETS99 ratio [95 % CI] | success diff [CI] | Holm p | Verdict |
|---|---|---|---|---|---|
| L1 col3p | ours Kc2+I11 vs B1 comparator (B1_best) | 0.143 [0.080, 0.221] | +8.0 pp [+2.0, +14.7] | 0.001 | win |
| L1 col4p | same | 0.003 [0.001, 0.006] | +92.0 pp [+84.7, +97.3] | 0.001 | win |
| L2 Max-Cut | ours none vs B1 comparator (B1_best) | 0.652 [0.652, 0.652] | 0 | 0.001 | win (area 0.80) |
| L2 Max-Cut | ours none vs B3 | 1.885 [0.000, 6.280] | +10 pp [-32, +55] | 1.000 | inconclusive |
| L3 150 sw | ours Kc2+I11 vs B1 (150 sw) | 3.366 [1.525, 5.411] | -30 pp [-46, -16] | 1.000 | loss |
| L3 300 sw | same | 3.226 [1.480, 60.4] | -22 pp [-41, -6] | 1.000 | loss |
| L3 600 sw | same | 3.240 [1.503, 78.5] | -19 pp [-40, -1] | 1.000 | loss |

- **L1 CONFIRMED** on both fresh colouring families (registered requirement). Successes: Kc2+I11 98.0 % (col3p) and
  99.3 % (col4p), against 90.0 % and 7.3 % for B1_best. B1_mesa_epoch and B3 reached 0 % on both. On col4p the very small ratio
  mainly reflects B1's 7 % success, so it says more about B1 failing than about a precise energy factor.
- **L2 CONFIRMED vs B1 on Max-Cut only** (single-family claim, as registered). It is a cost-model result, not an algorithm
  result: B1_best (b1.none) and ours_none produced **identical trajectories** (best E equal on 100/100 Max-Cut, 150/150 per
  colouring family runs), so the ratio is our hardware price table vs B1's for the same search. The same holds on col3p/col4p
  (0.713). Against B3 it is inconclusive (B3 32 % vs ours 42 % success, wide CI). L2 vs B2 not applicable (QKP only).
- **L3 FAILED.** The gap shrinks with budget (-30, -22, -19 pp) but does not close; it is a loss at every budget. Kc2+I11 on
  Max-Cut succeeds 12 / 20 / 23 % vs 42 % for B1 at 150 sweeps.

## Restart-threshold sweep (H6-R)
Selected on TUNE (lowest mean normalised end gap):

| Family | Kc2 (K x n, L) | MESA-epoch (K x n) | DA offset |
|---|---|---|---|
| Max-Cut | K 0.5, L 10 (129 restarts/run on TUNE) | K 40 (1.5/run; 25 % never) | div 0.5 (tie, never triggered) |
| col3p | K 1, L 10 (73) | K 40 (2.2) | div 0.5 (tie, never triggered) |
| col4p | K 2, L 10 (39) | K 20 (5.8) | div 0.5 (tie, never triggered) |

TEST: no restart rule beat no-restart anywhere. Max-Cut success none 42 % vs Kc2 23 %, MESA 10 %, DA 32 % (all inconclusive on
energy; MESA a quality loss). Colouring: all three swept arms 0 % vs 90 % (col3p) / 7.3 % (col4p) for no-restart: quality loss,
energy not evaluable.
- **DA offset: never triggered** (0 restarts in every config and every family; all six divisors give identical results). The
  knob is inert in this range. Its TEST success differs from ours_none (Max-Cut 32 % vs 42 %) without any restart; the cause is not established here.
- **Kc2 and MESA: triggered but unhelpful** (Kc2 39-130 restarts per run, MESA 1.6-5.7; never-triggered fraction 0-6 %).
- Note: the colouring win of Kc2+I11 (L1) does not come from Kc2 alone: the swept Kc2 arm without I11 scores 0 %. I11 carries it.

## I7v2
- **fs (ADC full scale = max column sum, lossless): a win** in all three families, ETS99 ratio vs v1 0.727 (Max-Cut),
  0.734 (col3p), 0.747 (col4p), equal success, Holm p 0.001.
- **I7v2 over fs: FAILED.** ours_none: Max-Cut 2.57 inconclusive (-26 pp), col3p 1.78 loss (-19 pp), col4p 0.49
  inconclusive [0.14, 1.24] (+6 pp). Kc2+I11: Max-Cut 4.57 inconclusive (-10 pp), col3p 3.57 loss (-73 pp), col4p 5.01 loss
  (-79 pp). The A3 LSB clamp (b_lo = b_hi, no I7 saving) applied to col3p 501, 502, 504 and col4p 521, 523.

## H5 re-run (report-only, graded score, Max-Cut, first 3 TEST instances x 10 seeds)
Graded score at nominal / ideal (dev_x0): ours_none 0.556 / 0.902, ours_kc2_i11 0.425 / 0.698, I7v2 0.389 / 0.843,
B1 (MESA epoch) 0.006 / 0.735. Escalation flag (nominal below ideal) is raised for every arm. Success at nominal is 0 % for all.

| 10 %-loss point | dev (x) | write (x) | drift (V/dec) | temp hot (C above 25) | supply low | mismatch (x) |
|---|---|---|---|---|---|---|
| ours_none | 1.12 | 2.99 | 0.0094 | 45 | 0.050 | 1.47 |
| ours_kc2_i11 | 1.12 | none in range | 0.0062 | 30 | 0.055 | 1.32 |
| I7v2 | 1.11 | 1.91 | 0.0041 | 17 | 0.030 | 1.12 |
| B1 | 1.10 | n/a | n/a | n/a | n/a | n/a |

Read axis and cold/high-supply: no 10 % loss in range for any arm. H5-a ratio ours/B1 exists only for dev (about 1.02, i.e.
equal) and read (both none in range); other axes have no B1 run. I7v2 is the least robust arm on every axis. B2 (QKP)
success: nominal 57 %, dev_x0 72 %, dev_x2 52 %, dev_x4 41 %, read_x2 45 %, read_x4 40 % (false-accept states 0 at dev_x0,
120-250 elsewhere). The main finding of H5: at the stand-in nominal variation every arm already loses a large part of its ideal
quality; device variation (dev axis loss point near 1.1x nominal) is the binding limit.

## Limits
- Leads L1-L3 were picked post hoc from Stage 2; only fresh Stage 3 data are used here, but the choice of what to test was
  data-driven.
- All baselines (B1, B3) are our own implementations priced by our cost model, not published chips. B1/B3 published numbers
  were not reproduced (Stage 2 finding). B1 comparator = lower observed ETS99 of two B1 variants on TEST (outside the bootstrap).
- L2 compares identical search trajectories under two price tables; it is an architecture-cost claim.
- I10 savings are negligible and are removed from all ours arms ("off" pricing).
- t_clk and area come from literature-based stand-in models, not timing closure or layout.
- MaxSAT not tested; no MaxSAT claim follows.

## Bottom line
Confirmed on fresh data: L1 (Kc2 + I11 beats B1 on colouring, both families, with higher success) and L2 (same search costs
about 35 % less energy on our hardware than on B1's, Max-Cut). Also confirmed: the lossless ADC full scale (fs) saves about
25 % energy. Failed: L3 (more sweeps do not let Kc2+I11 catch B1 on Max-Cut), I7v2, and every tuned restart rule (DA offset
never fires). Device variation remains the dominant robustness risk.
