# H6 follow-up: amendment 1 (committed before any Stage 3 run; H6_followup.md is not edited)

Basis: the pre-Stage 3 internal review (pin 905444e, verdict: not ready, 2 MAJOR + MINORs). No Stage 3 data exist, so these
changes are pre-run design corrections, not data-driven re-tuning. Where this file and H6_followup.md disagree, this file wins.

## A1. MESA epoch harness (MAJOR 1)
Defect: the stall rule restarts after K steps without a new best; every K of the section 4 grid (n/8 .. 4n) is shorter than the
10-sweep epoch (10 n steps), so MESA restarted before it could cool (G8, 150 sweeps: 139-146 restarts, best E -1321/-1934 vs target
-1984.95).
Change: for MESA only, K is swept at 1x, 2x, 4x the epoch, K in {10 n, 20 n, 40 n} steps (plan_h6.MESA_K_MULTS); the MESA sweep has 3
configs instead of 6 (K < epoch is dropped as degenerate). B1_mesa_epoch uses K = 1 epoch = 10 n (was K = n). Kc2 and DA-offset
grids, percentile pairs, epoch length (P4.02a, 10 sweeps) and the selection rule are unchanged.
Local evidence (one run each, G8, seed 0, 150 sweeps, Stage 2 tuned percentile pair; scratch outputs, not data; target E -1984.95,
best-known cut 2005): K = n: 146 restarts, E -1321; K = 10 n: 11 restarts, -1964 (98.0 %); K = 20 n: 5 restarts, -1980 (98.8 %);
K = 40 n: 2 restarts, -1980 (98.8 %). B1 MESA (b1.mesa) gives K = n: 146 restarts, -1321; K = 10 n: 11 restarts, -1964. MESA now
cools and restarts a handful of times; the 99 % target is still not guaranteed in one run.

## A2. H5 graded metric (MAJOR 2)
Defect: nominal success at the 99 % target is about 0 for the I7-free arms, so the success-based 10 %-loss point is undefined.
Change (primary H5 metric, success rate stays as secondary and is still reported):
- per run: gap = (E - E_ref)/|E_ref| (evalcommon.gap_of); graded score s = max(0, 1 - gap/0.10), i.e. 1 at best-known and 0 at a 10 %
  shortfall; per point: mean s, mean best-cut fraction of best-known (= 1 - mean gap, Max-Cut) and, for colouring families, mean
  conflicts (end-of-budget energy, 0 = proper colouring). H5 stays Max-Cut only, so conflicts are implemented but not populated.
- 10 %-loss point per axis = the existing rule (evaluate_h5.loss_point: smallest level with value < 0.9 x nominal, linear
  interpolation) applied to mean s; nominal-below-ideal escalation = mean s(nominal) < mean s(dev_x0) - 0.01. No bootstrap CI for
  these (report-only).
- evaluate_h6.h5_report/markdown output cut_frac, score, conflicts, graded loss points and the graded escalation flag.

## A3. I7v2 LSB (MINOR 2)
b_lo = b_hi - 1 gives LSB 4 when fs = 2^b - 2 or 2^b - 1 (col3p 501, 502, 504 with fs 7; col4p 521, 523 with fs 15). Clamp: in that
case b_lo = b_hi (LSB 1, I7 saves nothing on that instance). Result: the low-bits ADC error is at most one cell for every
instance (machines.i7v2_bits; test over fs 3..69 and 143). Colouring fs is only 7-15, so even LSB 2 is coarse; an H6-I7v2 reading
"breaks colouring" there is a valid finding and the report must name the clamped instances.

## A4. Other MINORs
- Gate: run_cell --smoke-h6 now also runs the select_h6 and report_h6 evaluators on the smoke records (barrier coverage).
- H5 B1: B1 (MESA epoch, K = 1 epoch, Stage 2 tuned b1.mesa pair) runs on 6 points (nominal, dev_x0, dev_x2, dev_x4, read_x2, read_x4),
  same 3 instances x 10 seeds; the H5-a ratio of graded 10 %-loss points ours/B1 is then available for the dev and read axes only
  (report-only). The other axes have no B1 value, which the report must say.
- Tuning split: seeds per tune instance widened from 4 to 8 (instances unchanged; no fresh 800-node Max-Cut graph is left).
- B1 comparator selection (lower observed ETS99 on TEST) is not part of the bootstrap; quote L1-L3 with that caveat.
- Barrier timeout 30 min kept; if report_h6 exceeds it, rerun it manually on the collected raw data.

## A5. Compute (section 7 replaced)
Jobs 32.6 CPU-h (tune 2.2, test 11.8, H5 18.6; B1 perturbed seconds not measured, set to 78.4 x 26.3/18.2 s/run), x 1.15 + 12 vCPU-h
gate = 49.5 vCPU-h, about Rs 100 at Rs 2.01 / vCPU-h, ~1.6 h wall on 32 vCPU. Cap 60 vCPU-h.
